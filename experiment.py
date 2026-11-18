"""Matched evaluations, trace storage and replay."""
from collections import defaultdict
import gzip
import hashlib
import json
import math
import os
import random
import statistics
import time
from pathlib import Path

from decoder import METHODS, LABELS, OllamaScores, footprints, metrics, sample


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def panel_interval(values):
    """Percentile bootstrap of complete paired seed panels, conditional on the masks."""
    rng = random.Random(19317)
    n = len(values)
    draws = sorted(sum(rng.choices(values, k=n))/n for _ in range(3000))
    return [draws[74], draws[2924]]


def summarize(records, manifest):
    data = defaultdict(list)
    examples = defaultdict(dict)
    curves = defaultdict(list)
    for record in records:
        mask, seed, method = (record[k] for k in ("mask", "seed", "method"))
        k = mask.count("1")
        draws = [tuple(map(int, p)) for p in record["draws"]]
        data[k, method, seed].append(metrics(mask, draws))
        seen = set()
        curve = []
        for p in draws:
            seen.add(p)
            curve.append(len(seen) / 3**k)
        curves[k, method].append(curve)
        if seed == manifest["seeds"][0]:
            examples[mask][method] = record["draws"]
    levels = {}
    for k in manifest["levels"]:
        stats, paired, series = {}, {}, {}
        seed_means = {}
        for method in METHODS:
            panels = [[statistics.fmean(col) for col in zip(*data[k, method, seed])]
                      for seed in manifest["seeds"]]
            stats[method] = dict(zip(("validity", "uniqueness", "recovery"),
                                     [statistics.fmean(col) for col in zip(*panels)]))
            seed_means[method] = [p[2] for p in panels]
            series[method] = [statistics.fmean(z) for z in zip(*curves[k,method])]
        for method in METHODS:
            diff = [a-b for a,b in zip(seed_means["prefix"], seed_means[method])]
            paired[method] = {"mean": statistics.fmean(diff), "ci95": panel_interval(diff)}
        levels[str(k)] = {"metrics": stats, "contrasts": paired, "curves": series,
                          "masks": len(data[k, "prefix", manifest["seeds"][0]]),
                          "n": len(series["prefix"]), "solutions": 3**k}
    return dict(manifest=manifest, labels=LABELS, levels=levels, examples=examples)


def read_records(folder):
    with gzip.open(folder / "traces.jsonl.gz", "rt", encoding="utf-8") as f:
        yield from (json.loads(line) for line in f)


def run(args):
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "run.json").exists():
        raise ValueError("This directory contains a completed run. Choose another --out directory.")
    # Exclusive lock prevents two writers from mixing traces.
    lock = folder / ".running"
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    try:
        execute(args, folder)
    finally:
        lock.unlink(missing_ok=True)


def execute(args, folder):
    backend = OllamaScores(args.endpoint, args.model)
    seeds = list(range(args.seed, args.seed + args.seeds))
    manifest = {"version": 1, "model": backend.info, "levels": sorted(set(args.levels)),
                "seeds": seeds, "limit": args.limit, "strength": args.strength, "budget": args.budget,
                "upstream": "c69e9318577b34b5b896996571aefd4ba6053f58", "grid": 3, "height": 3,
                "benchmark": "HypoSpace / 3D", "temperature": 1}
    checkpoints = folder / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    config = folder / "configuration.json"
    if config.exists() and json.loads(config.read_text()) != manifest:
        raise ValueError("Checkpoint configuration differs. Use another --out directory.")
    write_json(config, manifest)
    records = []
    start = time.monotonic()
    for k in manifest["levels"]:
        masks = list(footprints(k))[:args.limit]
        for index, mask in enumerate(masks, 1):
            file = checkpoints / (mask + ".json")
            if file.exists():
                entry = json.loads(file.read_text())
                backend.cache.update(entry["scores"])
                backend.usage.update(entry["usage"])
            else:
                before = backend.usage.copy()
                rows = []
                for seed in seeds:
                    for method in METHODS:
                        draws, _ = sample(mask, seed, method, backend, args.budget or 3**k, args.strength)
                        rows.append(dict(mask=mask, seed=seed, method=method,
                                         draws=["".join(map(str,p)) for p in draws]))
                entry = dict(rows=rows, scores={key:v for key,v in backend.cache.items() if key.startswith(mask+"/")},
                             usage=dict(backend.usage-before))
                write_json(file, entry)
            records.extend(entry["rows"])
            print(f"k={k}  view {index:02}/{len(masks)}  {mask}  model requests={backend.usage['requests']}", flush=True)
    manifest["backend_usage"] = dict(backend.usage)
    manifest["distinct_model_prefixes"] = len(backend.cache)
    manifest["final_session_seconds"] = round(time.monotonic() - start, 2)
    write_json(folder / "scores.json", backend.cache)
    with gzip.open(folder / "traces.jsonl.gz.tmp", "wt", encoding="utf8") as f:
        for row in records:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    (folder / "traces.jsonl.gz.tmp").replace(folder / "traces.jsonl.gz")
    manifest["trace_sha256"] = hashlib.sha256((folder / "traces.jsonl.gz").read_bytes()).hexdigest()
    write_json(folder / "run.json", summarize(records, manifest))


def replay(folder):
    dataset = json.loads((folder / "run.json").read_text())
    manifest = dataset["manifest"]
    cache = json.loads((folder/"scores.json").read_text())
    def lookup(mask, prefix):
        return cache[mask + "/" + "".join(map(str, prefix))]
    digest = hashlib.sha256((folder/"traces.jsonl.gz").read_bytes()).hexdigest()
    if digest != manifest["trace_sha256"]:
        raise ValueError("Trace SHA-256 mismatch")
    n = 0
    records = []
    seen = set()
    for record in read_records(folder):
        mask, seed, method = (record[k] for k in ("mask","seed","method"))
        key = mask, seed, method
        if key in seen:
            raise ValueError(f"Repeated panel {key}")
        seen.add(key)
        draws, _ = sample(mask, seed, method, lookup, manifest["budget"] or 3**mask.count("1"), manifest["strength"])
        if ["".join(map(str,p)) for p in draws] != record["draws"]:
            raise ValueError(f"Replay mismatch at {key}")
        n += len(draws)
        records.append(record)
    expected = {(mask, seed, method) for k in manifest["levels"]
                for mask in list(footprints(k))[:manifest["limit"]] for seed in manifest["seeds"] for method in METHODS}
    computed = summarize(records, manifest)
    # Python 3.12 changed float summation. Bootstrap endpoints can differ by
    # one ULP between supported Python versions after every tuple matches.
    for k, level in computed["levels"].items():
        for method, contrast in level["contrasts"].items():
            archived = dataset["levels"][k]["contrasts"][method]["ci95"]
            if len(archived) != 2 or not all(math.isclose(x, y, abs_tol=1e-14, rel_tol=0)
                                            for x, y in zip(contrast["ci95"], archived)):
                raise ValueError(f"Bootstrap interval mismatch at level {k}, {method}")
            contrast["ci95"] = archived
    if expected != seen or computed != dataset:
        raise ValueError("Published panels or aggregate metrics differ from replay")
    print(f"Verified {n:,} proposals across {len(seen):,} panels, including displayed metrics and curves.")

