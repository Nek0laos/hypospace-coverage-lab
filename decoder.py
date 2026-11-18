"""Autoregressive height decoding and online coverage feedback. Standard library only."""
from collections import Counter
from itertools import combinations
from math import exp, log1p, log
import json
import random
import urllib.request


METHODS = ("model", "stratified", "marginal", "prefix", "uniform")
LABELS = {"model": "Qwen sampling", "stratified": "Voxel-count strata",
          "marginal": "Marginal counts", "prefix": "Prefix counts", "uniform": "Uniform IID"}
HEIGHT = 3


def footprints(columns):
    for positions in combinations(range(9), columns):
        yield "".join("1" if i in positions else "0" for i in range(9))


def prompt(mask, prefix):
    grid = "\n".join(" ".join(mask[i:i+3]) for i in range(0, 9, 3))
    task = (f"A 3 by 3 top projection of a stack of unit cubes is:\n{grid}\n"
            f"A 1 is a nonempty vertical column, and a 0 is empty. All cubes are supported. "
            f"Heights range from 1 to 3 in nonempty columns. Propose one possible structure. "
            f"List only the {mask.count('1')} nonempty column heights in row-major order as a "
            "comma-separated list inside square brackets.")
    # The partial assistant turn is intentional: score the next possible digit.
    return ("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
            f"<|im_start|>user\n{task}<|im_end|>\n<|im_start|>assistant\n["
            + "".join(f"{value}," for value in prefix))


def api(base, path, body=None):
    req = urllib.request.Request(base.rstrip("/") + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


class OllamaScores:
    """Query raw token log probabilities on demand. Never substitute missing scores."""
    def __init__(self, endpoint, model):
        tags = api(endpoint, "/api/tags")["models"]
        tag = next((item for item in tags if item["name"] == model), None)
        if not tag:
            raise ValueError(f"Model {model!r} unavailable at the Ollama endpoint")
        self.info = {k: tag[k] for k in ("name", "digest", "details")}
        self.info["ollama"] = api(endpoint, "/api/version")["version"]
        self.endpoint, self.model = endpoint, model
        self.cache = {}
        self.usage = Counter()

    def __call__(self, mask, prefix):
        key = mask + "/" + "".join(map(str, prefix))
        if key in self.cache:
            return self.cache[key]
        scores = {}
        for digit in (1, 2, 3):
            if str(digit) in scores:
                continue
            # A singleton grammar exposes the raw chosen-token logprob even if a
            # digit falls outside the server's top list. The prompt stays fixed.
            result = api(self.endpoint, "/api/generate", {
                "model": self.model, "prompt": prompt(mask, prefix), "raw": True, "stream": False,
                "format": {"type": "integer", "enum": [digit]}, "logprobs": True, "top_logprobs": 20,
                "options": {"num_predict": 1, "temperature": 1, "top_k": 0, "top_p": 1,
                            "repeat_penalty": 1, "seed": 42, "num_ctx": 1024}})
            self.usage.update({"requests": 1, "prompt_tokens_reported": result.get("prompt_eval_count", 0),
                               "generated_tokens": result.get("eval_count", 0)})
            pos = result["logprobs"][0]
            if pos["token"] != str(digit):
                raise RuntimeError(f"Backend did not return requested single digit {digit}: {pos['token']!r}")
            for token in [*pos["top_logprobs"], pos]:
                if token["token"] in ("1", "2", "3"):
                    scores[token["token"]] = token["logprob"]
        self.cache[key] = [scores[str(i)] for i in (1, 2, 3)]
        return self.cache[key]


def complexity_schedule(columns, budget, rng):
    # Coefficients of (x+x^2+x^3)^columns. The stratum control gets exact sizes.
    sizes = Counter({0: 1})
    for _ in range(columns):
        nxt = Counter()
        for total, n in sizes.items():
            for height in (1, 2, 3):
                nxt[total + height] += n
        sizes = nxt
    targets = [total for total, n in sorted(sizes.items()) for _ in range(n)]
    cycles, remainder = divmod(budget, len(targets))
    schedule = targets * cycles + rng.sample(targets, remainder)
    rng.shuffle(schedule)
    return schedule


def probabilities(values):
    weights = [exp(v - max(values)) for v in values]
    total = sum(weights)
    return [w / total for w in weights]


def distribution(logps, counts, allowed, strength, calibrate=True, flatten=False):
    # One visit can offset even sharp model preferences. Finite penalties keep
    # every grammar-admissible action reachable.
    scale = 1 + (max(logps) - min(logps)) / log(2) if calibrate else 1.
    base = [0., 0., 0.] if flatten else logps
    values = [base[h-1] - strength * scale * log1p(counts[h]) for h in allowed]
    return probabilities(values)


def sample(mask, seed, method, scores, budget, strength=1., explain=False, calibrate=True, flatten=False):
    columns = mask.count("1")
    # Stable per-(mask,seed) streams; methods share the same base uniforms.
    rng = random.Random((seed << 10) + int(mask, 2))
    sched_rng = random.Random((seed << 11) + int(mask, 2))
    targets = complexity_schedule(columns, budget, sched_rng) if method == "stratified" else None
    visits = Counter()
    proposals, trace = [], []
    for t in range(budget):
        prefix = ()
        updates, decisions = [], []
        for j in range(columns):
            context = (j,) if method == "marginal" else prefix
            counts = {h: visits[context, h] for h in (1, 2, 3)}
            allowed = [1, 2, 3]
            if targets is not None:
                remaining = columns - j - 1
                allowed = [h for h in allowed if remaining <= targets[t] - sum(prefix) - h <= 3 * remaining]
            logps = [0., 0., 0.] if method == "uniform" else scores(mask, prefix)
            feedback = strength if method in ("marginal", "prefix") else 0.
            probs = distribution(logps, counts, allowed, feedback, calibrate, flatten)
            height = rng.choices(allowed, weights=probs)[0]
            if explain:
                decisions.append(dict(prefix=list(prefix), raw=logps, counts=counts, allowed=allowed,
                                      probability=probs, selected=height))
            updates.append((context, height))
            prefix += (height,)
        proposals.append(prefix)
        visits.update(updates)
        if explain:
            trace.append(decisions)
    return proposals, trace


def metrics(mask, proposals):
    # A tuple is a complete canonical structure in the height representation.
    k = mask.count("1")
    valid = [p for p in proposals if len(p) == k and all(type(h) is int and 1 <= h <= 3 for h in p)]
    return (len(valid) / len(proposals), len(set(proposals)) / len(proposals), len(set(valid)) / 3**k)

