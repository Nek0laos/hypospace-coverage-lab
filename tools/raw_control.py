"""Run or replay the six-mask Qwen raw-layer comparison with the upstream scorer.

Uses the same upstream checkout and dependencies as verify_upstream.py. Point
--endpoint at Ollama. --replay verifies a completed run without contacting it.

    python tools/raw_control.py --upstream ../_HypoSpace --out results/raw-control
    python tools/raw_control.py --upstream ../_HypoSpace --out results/raw-control --replay
"""

import argparse
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
import sys
import tempfile
from urllib.request import Request, urlopen

from verify_upstream import REVISION, check_upstream, require


MODEL = "qwen2.5:3b"
SEED = 33550336
MASK_COUNT = 6
ATTEMPTS = 27
HISTORY_LIMIT = 10
OPTIONS = {"temperature": 1.0, "top_p": 1.0, "top_k": 0, "repeat_penalty": 1.0,
           "num_predict": 192, "num_ctx": 4096}


def get_json(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_records(path):
    rows = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            key = row["mask"], row["attempt"]
            require(key not in rows, f"Duplicate row {key}")
            rows[key] = row
    return rows


class RecordedQueries:
    def __init__(self, mask, instance_index, args, saved, stream):
        self.mask = mask
        self.instance_index = instance_index
        self.args = args
        self.saved = saved
        self.stream = stream
        self.attempt = 0

    def query(self, prompt):
        try:
            return self.query_once(prompt)
        except Exception as error:
            # Upstream catches Exception and advances to the next draw. A
            # transport or replay error makes this run incomplete and must stop it.
            raise SystemExit(f"Stopped at {self.mask} attempt {self.attempt}: {error}") from error

    def query_once(self, prompt):
        self.attempt += 1
        key = (self.mask, self.attempt)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        if key in self.saved:
            row = self.saved[key]
            require(row["prompt_sha256"] == prompt_hash, f"Prompt mismatch for {key}")
            return row["response"]
        require(not self.args.replay, f"Missing recorded response {key}")
        seed = SEED + self.instance_index * ATTEMPTS + self.attempt - 1
        result = get_json(self.args.endpoint.rstrip("/") + "/api/chat", {
            "model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "stream": False, "options": {**OPTIONS, "seed": seed}
        })
        require(result.get("done") and isinstance(result.get("message", {}).get("content"), str),
                f"Incomplete provider response for {key}")
        row = {"mask": self.mask, "attempt": self.attempt, "sampling_seed": seed,
               "prompt_sha256": prompt_hash, "response": result["message"]["content"],
               "done_reason": result.get("done_reason"),
               "prompt_tokens": result.get("prompt_eval_count", 0),
               "completion_tokens": result.get("eval_count", 0),
               "total_duration_ns": result.get("total_duration", 0)}
        self.stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.stream.flush()
        self.saved[key] = row
        return row["response"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("results/raw-control"))
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    directory = (args.upstream / "3d").resolve()
    check_upstream(directory)
    sys.path.insert(0, str(directory))
    from generate_3d_dataset_complete import Dataset3DGenerator
    from run_3d_benchmark import Benchmark3D

    class LimitedHistory(Benchmark3D):
        def create_prompt(self, observations, prior_structures=None):
            return super().create_prompt(observations, (prior_structures or [])[-HISTORY_LIMIT:])

    generator = Dataset3DGenerator(grid_size=3, max_height=3, max_blocks=3)
    generator.generate_all_top_views(fixed_blocks=True)
    generator.generate_all_structures()
    generator.generate_observation_sets()
    with tempfile.TemporaryDirectory() as temporary:
        dataset = Path(temporary) / "dataset.json"
        generator.save_dataset(str(dataset))
        evaluator = LimitedHistory(str(dataset))
    observations = random.Random(SEED).sample(evaluator.all_observation_sets, MASK_COUNT)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "responses.jsonl"
    metadata = args.out / "protocol.json"
    config = {"upstream_commit": REVISION, "model": MODEL, "options": OPTIONS,
              "mask_sampling_seed": SEED,
              "sampling_seed_rule": "mask_sampling_seed + 27 * zero_based_mask_index + zero_based_attempt",
              "masks": [obs["observation"] for obs in observations],
              "attempts_per_mask": ATTEMPTS, "max_prior_distinct_parsed_structures": HISTORY_LIMIT,
              "attempts_per_request": 1, "endpoint_type": "Ollama /api/chat"}
    saved = load_records(path)
    protocol = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
    if args.replay:
        require(protocol, "The run protocol is required for replay")
    else:
        endpoint = args.endpoint.rstrip("/")
        tags = get_json(endpoint + "/api/tags")["models"]
        model = next(model for model in tags if model["name"] == MODEL)
        config.update({"model_digest": model["digest"], "quantization": model["details"]["quantization_level"],
                       "ollama_version": get_json(endpoint + "/api/version")["version"]})
    if protocol:
        require(all(protocol.get(k) == v for k, v in config.items()), "Protocol differs from existing run")
    else:
        require(not saved, "Cannot resume responses without their protocol")
        write_json(metadata, config)
    results = []
    with path.open("r" if args.replay else "a", encoding="utf-8") as stream:
        for i, observation in enumerate(observations):
            client = RecordedQueries(observation["observation"], i, args, saved, stream)
            metrics = evaluator.evaluate_single_observation_set(
                client, observation, n_queries=ATTEMPTS, verbose=False, max_retries=1
            )
            require(client.attempt == ATTEMPTS, "Unexpected attempt count from upstream evaluator")
            results.append({"mask": client.mask, **{key: metrics[key] for key in (
                "n_ground_truths", "n_queries", "n_valid", "n_unique", "n_recovered_gts",
                "parse_success_count", "valid_rate", "novelty_rate", "recovery_rate")}})
            print(f"Mask {i + 1}/{len(observations)} {client.mask} | "
                  f"valid {metrics['n_valid']}/{ATTEMPTS} | recovered {metrics['n_recovered_gts']}/27", flush=True)
    require(len(saved) == ATTEMPTS * MASK_COUNT, "Run contains missing or extraneous responses")
    summary = {"masks": results,
               "attempts": len(saved),
               "mean": {k: mean(row[k] for row in results)
                        for k in ("valid_rate", "novelty_rate", "recovery_rate")},
               "prompt_tokens": sum(r["prompt_tokens"] for r in saved.values()),
               "completion_tokens": sum(r["completion_tokens"] for r in saved.values()),
               "responses_at_length_limit": sum(r["done_reason"] == "length" for r in saved.values())}
    if args.replay:
        require(json.loads((args.out / "summary.json").read_text(encoding="utf-8")) == summary,
                "Replayed metrics differ from the published summary")
    else:
        write_json(args.out / "summary.json", summary)
    print(json.dumps(summary["mean"]))


if __name__ == "__main__":
    main()
