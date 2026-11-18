"""Separate the effect of count feedback, model preferences and scale calibration."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from decoder import sample, metrics
from experiment import panel_interval, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("results/reference"))
    parser.add_argument("--out", type=Path, default=Path("results/ablation.json"))
    args = parser.parse_args()
    data = json.loads((args.run / "run.json").read_text())
    manifest = data["manifest"]
    table = json.loads((args.run / "scores.json").read_text())
    def model(mask, prefix):
        return table[mask + "/" + "".join(map(str,prefix))]
    def flat(mask, prefix):
        return [0., 0., 0.]
    result = {"seeds":manifest["seeds"], "trace_sha256":manifest["trace_sha256"], "levels":{}}
    for k in manifest["levels"]:
        masks = [m for m in data["examples"] if m.count("1") == k]
        budget = data["levels"][str(k)]["n"]
        per_seed = {}
        controls = [("prefix", model, True, False), ("fixed_scale", model, False, False),
                    ("flat_logits", flat, True, False), ("flat_with_model_scale", model, True, True)]
        for name, scorer, calibrated, flatten in controls:
            seed_means = []
            for seed in manifest["seeds"]:
                scores = []
                for mask in masks:
                    proposals, _ = sample(mask, seed, "prefix", scorer, budget, manifest["strength"],
                                          calibrate=calibrated, flatten=flatten)
                    scores.append(metrics(mask, proposals)[2])
                seed_means.append(statistics.fmean(scores))
            per_seed[name] = seed_means
        summary = {}
        for name, values in per_seed.items():
            differences = [a-b for a,b in zip(per_seed["prefix"],values)]
            summary[name] = {"recovery":statistics.fmean(values),"prefix_minus_control":statistics.fmean(differences),
                             "delta_ci95":panel_interval(differences)}
        result["levels"][k] = summary
    write_json(args.out,result)
    print(json.dumps(result["levels"],indent=2))


if __name__ == "__main__":
    main()

