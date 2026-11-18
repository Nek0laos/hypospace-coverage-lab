"""Command line entry point. Run python lab.py --help."""
import argparse
import cmd
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path

from decoder import METHODS, prompt, sample
from experiment import replay, run

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "results" / "reference"
DEBUG_POLICIES = (*METHODS, "fixed_scale", "flat_logits", "flat_with_model_scale")


def inspect_draw(args):
    dataset = json.loads((args.run / "run.json").read_text())
    manifest = dataset["manifest"]
    mask = args.mask or next(m for m in dataset["examples"] if m.count("1") == max(manifest["levels"]))
    if mask not in dataset["examples"] or args.seed is not None and args.seed not in manifest["seeds"]:
        raise ValueError("Choose a footprint and seed from the selected run")
    budget = manifest["budget"] or 3**mask.count("1")
    step = args.step if args.step is not None else budget
    if not 1 <= step <= budget:
        raise ValueError(f"Step must be between 1 and {budget}")
    scores = json.loads((args.run/"scores.json").read_text())
    def lookup(mask, prefix):
        if args.method == "flat_logits":
            return [0., 0., 0.]
        return scores[mask + "/" + "".join(map(str,prefix))]
    seed = manifest["seeds"][0] if args.seed is None else args.seed
    policy = args.method if args.method in METHODS else "prefix"
    draws, decisions = sample(mask, seed, policy, lookup, budget, manifest["strength"], explain=True,
                              calibrate=args.method != "fixed_scale", flatten=args.method == "flat_with_model_scale")
    if args.prompt:
        print(prompt(mask, ()))
    print(f"{manifest['model']['name']} | {args.method} | view {mask} | seed {seed}")
    seen = set()
    for i, p in enumerate(draws[:step], 1):
        print(f" {i:2}  {''.join(map(str,p))}  {'repeat' if p in seen else 'NEW':6}", end="")
        seen.add(p)
        print(f"  recovered {len(seen):2}/{3**mask.count('1')}")
    print(f"\nInside draw {step}")
    for d in decisions[step-1]:
        print(f" prefix={d['prefix']}  raw_logp={[round(x,3) for x in d['raw']]}  counts={list(d['counts'].values())}"
              f"  allowed={d['allowed']}  p={[round(x,3) for x in d['probability']]}  chose={d['selected']}")


def serve(args):
    report = (args.run/"run.json").read_bytes()
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/run.json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(report)))
                self.end_headers()
                self.wfile.write(report)
            else:
                super().do_GET()
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=ROOT/"docs")) as server:
        print(f"Coverage Lab   http://127.0.0.1:{server.server_port}   (Ctrl+C to stop)", flush=True)
        server.serve_forever()


def shell(args):
    dataset = json.loads((args.run/"run.json").read_text())
    manifest = dataset["manifest"]
    args.mask = next(m for m in dataset["examples"] if m.count("1") == max(manifest["levels"]))
    args.method, args.seed, args.step, args.prompt = "prefix", manifest["seeds"][0], 1, False

    class Inspector(cmd.Cmd):
        prompt = "coverage> "
        intro = "Coverage debugger. Use next, back, goto N, policy NAME, mask BITS, seed N, prompt or quit."

        def emptyline(self):
            self.do_next("")

        def jump(self, step):
            budget = manifest["budget"] or 3**args.mask.count("1")
            args.step = max(1, min(budget, step))
            inspect_draw(args)

        def do_next(self, _):
            self.jump(args.step + 1)

        def do_back(self, _):
            self.jump(args.step - 1)

        def do_goto(self, value):
            if value.isdecimal():
                self.jump(int(value))
            else:
                print("goto takes a positive draw number")

        def do_policy(self, value):
            if value in DEBUG_POLICIES:
                args.method = value
                self.jump(args.step)
            else:
                print("Policies:", ", ".join(DEBUG_POLICIES))

        def do_mask(self, value):
            if value in dataset["examples"]:
                args.mask = value
                self.jump(1)
            else:
                print("Available footprints:", " ".join(sorted(dataset["examples"])))

        def do_seed(self, value):
            if value.isdecimal() and int(value) in manifest["seeds"]:
                args.seed = int(value)
                self.jump(1)
            else:
                print("Available seeds:", manifest["seeds"])

        def do_prompt(self, _):
            print(prompt(args.mask, ()))

        def do_quit(self, _):
            return True

        do_EOF = do_quit
        do_exit = do_quit

    inspect_draw(args)
    Inspector().cmdloop()


def main():
    parser = argparse.ArgumentParser(description="HypoSpace 3D coverage experiments")
    subs = parser.add_subparsers(dest="cmd", required=True)
    r = subs.add_parser("run", help="collect token evidence and sample matched policies")
    r.add_argument("--endpoint", default="http://127.0.0.1:11434")
    r.add_argument("--model", default="qwen2.5:3b")
    r.add_argument("--levels", nargs="+", type=int, choices=[1,2,3], default=[1,2,3])
    r.add_argument("--seeds", type=int, default=20)
    r.add_argument("--seed", type=int, default=101)
    r.add_argument("--limit", type=int, help="number of row-major footprints per level")
    r.add_argument("--budget", type=int, help="draws per view and seed (default: solution count)")
    r.add_argument("--strength", type=float, default=1.)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=run)
    for cmd, desc in [("inspect","step through an archived run"),("replay","verify draws from archived model scores"),
                      ("serve","open the presentation dashboard on localhost"),
                      ("shell","interactive per-token debugger for a recorded run")]:
        p = subs.add_parser(cmd, help=desc)
        p.add_argument("--run", type=Path, default=REFERENCE)
        if cmd == "inspect":
            p.add_argument("--mask", help="nine row-major footprint bits")
            p.add_argument("--seed", type=int)
            p.add_argument("--method", choices=DEBUG_POLICIES, default="prefix")
            p.add_argument("--step", type=int)
            p.add_argument("--prompt", action="store_true")
            p.set_defaults(fn=inspect_draw)
        elif cmd == "serve":
            p.add_argument("--port", type=int, default=8765)
            p.set_defaults(fn=serve)
        elif cmd == "shell":
            p.set_defaults(fn=shell)
        else:
            p.set_defaults(fn=lambda a:replay(a.run))
    args = parser.parse_args()
    if args.cmd == "run":
        if min(args.seeds, args.limit or 1, args.budget or 1) < 1 or args.budget == 0 or args.limit == 0 or args.seed < 0:
            parser.error("Seeds, limit and budget must be positive. The first seed must be nonnegative.")
        if not math.isfinite(args.strength) or args.strength < 0:
            parser.error("--strength must be finite and nonnegative")
    try:
        args.fn(args)
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()

