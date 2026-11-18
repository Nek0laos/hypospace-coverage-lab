"""Check the height encoding against a pinned upstream HypoSpace checkout.

Requires numpy, scipy, PyYAML, requests and networkx, which upstream imports.
From the project root, run

    git clone https://github.com/CTT-Pavilion/_HypoSpace.git ../_HypoSpace
    git -C ../_HypoSpace checkout c69e9318577b34b5b896996571aefd4ba6053f58
    python tools/verify_upstream.py --upstream ../_HypoSpace --out results/upstream-check.json

The audit generates ground truth offline. It is independent of model inference.
"""

import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np


REVISION = "c69e9318577b34b5b896996571aefd4ba6053f58"
SOURCES = {
    "generate_3d_dataset_complete.py": "b913792a85477290b6c9a1cbf7ba2e7f50234763",
    "run_3d_benchmark.py": "a2c8e014d4c5498927f504f0c2dafb8f764cb72d",
    "modules/llm_interface.py": "cc08a6e115c564d55581f9737a6fe33003f9aa43",
    "modules/models.py": "720447230bc966d432e5976d533e3ffdda464377",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_upstream(directory):
    for filename, expected in SOURCES.items():
        source = (directory / filename).read_bytes().replace(b"\r\n", b"\n")
        header = f"blob {len(source)}\0".encode()
        actual = hashlib.sha1(header + source).hexdigest()
        require(actual == expected, f"Unexpected version of upstream {filename}")


def decode(mask, heights):
    side = math.isqrt(len(mask))
    field = np.zeros(len(mask), dtype=int)
    field[[i for i, bit in enumerate(mask) if bit == "1"]] = heights
    field = field.reshape(side, side)
    return [(field >= level).astype(int).tolist() for level in range(1, max(heights) + 1)]


def ground_truth_keys(observation):
    return {(record["hash"], tuple(record["layers"])) for record in observation["ground_truth_structures"]}


def check_completions(observation, max_height, evaluator, structure_class):
    mask = observation["observation"]
    expected = ground_truth_keys(observation)
    observed = set()
    for heights in itertools.product(range(1, max_height + 1), repeat=mask.count("1")):
        layers = decode(mask, heights)
        proposal = structure_class(layers)
        parsed = evaluator.parse_llm_response("Structure:\n" + proposal.to_string())
        require(parsed is not None, f"Could not parse {mask=} {heights=}")
        require(evaluator.validate_structure_matches_observations(parsed, mask),
                f"Failed upstream projection/gravity check for {mask=} {heights=}")
        compact = tuple("".join(str(value) for row in level for value in row) for level in layers)
        observed.add((parsed.get_hash(), compact))
    expected_count = max_height ** mask.count("1")
    require(len({key for key, _ in observed}) == expected_count, f"Within-mask hash collision for {mask}")
    require(len(observed) == observation["n_compatible_structures"] == expected_count,
            f"Ground-truth size mismatch for {mask}")
    require(observed == expected, f"Voxel occupancy or hash differs from upstream for {mask}")
    return expected_count


class Replay:
    """Feed a known response stream through the upstream evaluator without an API."""

    def __init__(self, responses):
        self.responses = iter(responses)

    def query(self, prompt):
        return next(self.responses)


def check_metric_probe(observation, evaluator, structure_class):
    mask = observation["observation"]
    count = mask.count("1")
    ground = decode(mask, (1,) * count)
    second = decode(mask, (2,) + (1,) * (count - 1))
    zero_layer = np.zeros((3, 3), dtype=int).tolist()
    floating = [zero_layer, ground[0]]
    wrong_projection = decode(mask.replace("0", "1", 1), (1,) * (count + 1))
    responses = [
        "Structure:\n" + structure_class(layers).to_string()
        for layers in [ground, ground, second, floating, wrong_projection]
    ] + ["unparseable"]
    metrics = evaluator.evaluate_single_observation_set(
        Replay(responses), observation, n_queries=len(responses), verbose=False, max_retries=1
    )
    expected = {"n_queries": 6, "n_valid": 3, "n_unique": 4,
                "n_recovered_gts": 2, "parse_success_count": 5}
    require(all(metrics[key] == value for key, value in expected.items()),
            f"Unexpected official counts for the mixed-stream probe on {mask}")
    require(metrics["valid_rate"] == 3 / 6 and metrics["novelty_rate"] == 4 / 6
            and metrics["recovery_rate"] == 2 / observation["n_compatible_structures"],
            f"Unexpected official rates on {mask}")
    return expected


def check_traces(path, evaluator, structure_class):
    """Score each published trial with the official text parser and metrics."""
    by_mask = {obs["observation"]: obs for obs in evaluator.all_observation_sets}
    trials = set()
    totals = defaultdict(lambda: {"trials": 0, "draws": 0, "vr_sum": 0, "nr_sum": 0, "rr_sum": 0})
    # Replay always returns the recorded proposal irrespective of the prompt.
    # Skip unused prompt rendering and cache the pure upstream text parser.
    evaluator.create_prompt = lambda *args, **kwargs: ""
    evaluator.parse_llm_response = lru_cache(maxsize=None)(evaluator.parse_llm_response)

    @lru_cache(maxsize=None)
    def response_text(mask, sample):
        layers = decode(mask, tuple(int(digit) for digit in sample))
        return "Structure:\n" + structure_class(layers).to_string()

    read = gzip.open if path.suffix == ".gz" else open
    with read(path, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            mask, method, draws = row["mask"], row["method"], row["draws"]
            key = (mask, method, row["seed"])
            require(key not in trials, f"Duplicate trace {key}")
            trials.add(key)
            observation = by_mask[mask]
            responses = []
            for sample in draws:
                require(len(sample) == mask.count("1") and set(sample) <= set("123"),
                        f"Out-of-grammar draw {sample!r} in {key}")
                responses.append(response_text(mask, sample))
            require(responses, f"Empty trace {key}")
            metrics = evaluator.evaluate_single_observation_set(
                Replay(responses), observation, n_queries=len(draws), max_retries=1, verbose=False
            )
            unique = len(set(draws))
            require(metrics["n_valid"] == metrics["parse_success_count"] == len(draws)
                    and metrics["n_unique"] == metrics["n_recovered_gts"] == unique,
                    f"Tuple metrics differ from official metrics for {key}")
            group = totals[method]
            group["trials"] += 1
            group["draws"] += len(draws)
            group["vr_sum"] += metrics["valid_rate"]
            group["nr_sum"] += metrics["novelty_rate"]
            group["rr_sum"] += metrics["recovery_rate"]
    require(trials, f"No records in {path}")
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "trials": len(trials),
        "official_macro_means_by_method": {
            method: {"trials": sums["trials"], "draws": sums["draws"],
                     **{m: sums[m + "_sum"] / sums["trials"] for m in ("vr", "nr", "rr")}}
            for method, sums in sorted(totals.items())
        }
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True, help="root of the pinned _HypoSpace checkout")
    parser.add_argument("--out", type=Path, help="optional JSON output file")
    parser.add_argument("--traces", type=Path, help="optional raw JSONL or JSONL.GZ trial file")
    args = parser.parse_args()
    directory = (args.upstream / "3d").resolve()
    check_upstream(directory)
    sys.path.insert(0, str(directory))
    from generate_3d_dataset_complete import Dataset3DGenerator
    from run_3d_benchmark import Benchmark3D, Structure3D

    generator = Dataset3DGenerator(grid_size=3, max_blocks=3, max_height=3)
    generator.generate_all_top_views()
    generator.generate_all_structures()
    generator.generate_observation_sets()
    with TemporaryDirectory() as directory:
        dataset = Path(directory) / "dataset.json"
        generator.save_dataset(str(dataset))
        evaluator = Benchmark3D(str(dataset))
        stats = {k: {"observations": 0, "structures": 0} for k in (1, 2, 3)}
        masks = set()
        for observation in evaluator.all_observation_sets:
            mask = observation["observation"]
            require(mask not in masks, f"Repeated observation {mask}")
            masks.add(mask)
            group = stats[mask.count("1")]
            group["observations"] += 1
            group["structures"] += check_completions(observation, 3, evaluator, Structure3D)
            probe_counts = check_metric_probe(observation, evaluator, Structure3D)

    for k, group in stats.items():
        require(group["observations"] == math.comb(9, k), f"Missing masks in group {k}")
    report = {
        "upstream_url": "https://github.com/CTT-Pavilion/_HypoSpace",
        "upstream_commit": REVISION,
        "verified_git_blobs": SOURCES,
        "grid_size": 3,
        "max_height": 3,
        "columns_in_row_major_order": True,
        "by_occupied_columns": stats,
        "total_observations": len(masks),
        "total_unique_completions_checked": sum(group["structures"] for group in stats.values()),
        "checks": ["serialized layers", "canonical upstream hash", "upstream text parser",
                   "top-view projection", "gravity support", "per-mask set equality"],
        "mixed_stream_probes": len(masks),
        "official_counts_per_six_attempt_probe": probe_counts,
        "status": "passed"
    }
    if args.traces:
        report["trace_replay"] = check_traces(args.traces, evaluator, Structure3D)
    output = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
