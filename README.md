# HypoSpace Coverage Lab

At a budget of 27 proposals for 27 legal structures, Qwen2.5-3B recovered **79.66%** of the solution set with prefix-count decoding and **19.73%** with ordinary constrained sampling. Both used the same frozen model, prompt, digit grammar and budget. Results cover all 84 three-column top views of a 3 × 3 grid and 20 paired sampling seeds on an RTX 4080 SUPER.

[Interactive experiment](https://nek0laos.github.io/hypospace-coverage-lab/) · [10-minute presentation](https://github.com/Nek0laos/hypospace-coverage-lab/releases/tag/v1.0) · [HypoSpace paper](https://proceedings.mlr.press/v306/chen26bz.html)

## Try the experiment

Python 3.10+ with its standard library is sufficient for the archived experiments, debugger and dashboard. Commands below start in the repository root.

```sh
python lab.py shell
python lab.py serve
python lab.py replay
```

Open **http://127.0.0.1:8765** after starting the server. Select one to three occupied columns, toggle comparison curves, choose a footprint and play its recorded proposals. The chart averages every seed and footprint in the selected difficulty. The voxel player follows a single recorded run. The public dashboard uses the same data.

At the `coverage>` prompt, use `mask 001010100`, `policy prefix`, `goto 12`, `back`, `next`, `seed 102`, `prompt` or `quit`. Each draw shows raw model log probabilities for heights 1–3, past visits, the permitted heights, the final sampling probabilities and the selected height. A single noninteractive inspection also works.

```sh
python lab.py inspect --mask 001010100 --method prefix --seed 101 --step 12 --prompt
```

**中文速用**　在项目根目录运行 `python lab.py shell` 进入调试终端，输入 `goto 12` 查看第 12 次生成过程中每个高度的概率。运行 `python lab.py serve` 后打开终端显示的网址，即可回放同一批实验。离线演示无需安装模型。

## Method

A top view marks the occupied cells. Every occupied cell supports a contiguous stack of one, two or three voxels. Read those heights in row-major order. For a footprint with three occupied columns, the sequence `[2,1,3]` identifies one complete structure. This representation is bijective under the benchmark’s gravity constraint. Each method uses the same height alphabet. The adapter applies the Qwen ChatML template and conditions on the actual top view and the partially generated list.

At prefix p, let l(h) be Qwen’s raw next-digit log probability, and C(p,h) the number of completed proposals in this run that traversed child h of p. Sample from

```text
s(p) = 1 + (max_h l(h) - min_h l(h)) / log(2)
q(h | p, history) = softmax_h [ l(h) - strength * s(p) * log(1 + C(p,h)) ]
```

The scale calibrates the exploration penalty to local model confidence. At strength 1, one visit carries enough penalty to overcome the full observed logit spread if the competing child is unvisited. The logarithm makes subsequent visits have diminishing influence. All permitted choices retain positive probability. Counters update only after the complete proposal and reset for each mask, seed and method. The policy consumes observed counts and model scores. It never queries the list of missing solutions. With a hash table, per-run state grows with the number of distinct prefix edges visited.

This project contributes the **spread-calibrated, prefix-conditional count rule and its controlled evaluation**. Count-based exploration and diverse sequence decoding have a substantial prior literature. Exact sampling without replacement can guarantee distinct sequences, and explicit enumeration reaches 100% in this small Cartesian space. [Bellemare et al.](https://proceedings.neurips.cc/paper_files/paper/2016/hash/afda332245e2af431fb7b672a68b659d-Abstract.html) · [Kool et al.](https://proceedings.mlr.press/v97/kool19a.html)

## Results

Mean recovery over all footprints at each difficulty, averaged over seeds 101 through 120. The proposal budget per view and seed equals the number of legal solutions. All five methods have 100% validity by construction. Under this budget, uniqueness and recovery have the same numerical value.

| Occupied columns | Views | Draw budget | Qwen sampling | Voxel-count strata | Marginal counts | Prefix counts | Uniform IID |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 9 | 3 | 58.33% | **100.00%** | 87.78% | 87.78% | 71.48% |
| 2 | 36 | 9 | 37.15% | 71.19% | 64.81% | **82.67%** | 65.14% |
| 3 | 84 | 27 | 19.73% | 44.19% | 45.78% | **79.66%** | 63.91% |

On three-column views, prefix counts gained **59.93 percentage points** over Qwen sampling, with a paired 95% bootstrap interval of **[59.70, 60.18]**. The bootstrap resamples 20 whole seed panels, retaining all 84 views and both decoders within each panel. It quantifies sampling-seed variability conditional on this fixed family and checkpoint. Prefix counts gained 33.88 points over position-only counts. On one-column views each total voxel count determines one solution, which explains the stratified control’s perfect recovery.

* **Qwen sampling** renormalizes Qwen’s next-token scores onto heights 1–3 at every column. Earlier proposals do not enter the prompt.
* **Voxel-count strata** adapts the paper’s complexity baseline. A dynamic program computes the exact histogram of total heights. Draws are allocated proportionally and randomly ordered, with a hard mask enforcing feasibility of the remaining sum. The original paper uses textual complexity prompts.
* **Marginal counts** uses the identical calibrated penalty but pools visits by column position. All earlier tuples with any prefix contribute to the same position counter.
* **Prefix counts** keeps a separate distribution of visits for each preceding sequence of heights.
* **Uniform IID** samples heights independently with equal probability and no LLM. For 27 equally likely structures in 27 draws, expected recovery is 1 − (26/27)^27 ≈ 63.90%.

The study measures the coverage of the **model plus decoder**. The specialized grammar supplies validity. The frozen weights receive no training. The experiment covers the voxel task, and claims about the other two HypoSpace domains or other checkpoints require further experiments. The main protocol changes the output format and context relative to the official layer-text runner. The paper’s published model scores use their own generation protocol.

## Reproduce with the model

A separate ablation on the same 84 three-column views gave 30.83% recovery when the count multiplier was fixed at one. Setting all model scores to zero and applying the same prefix policy gave 74.83%. The latter also sets the score-spread term to zero. Its 4.83-point gap to the full method measures the joint effect of model preferences and the calibration they induce. These controls are in [the ablation results](results/ablation.json).

The reference model is Ollama `qwen2.5:3b`, Q4_K_M, manifest digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`, served by Ollama 0.31.2. The adapter expects Qwen2.5 ChatML and single-token decimal digits. On a machine with Ollama, start its service, then run the following. An existing endpoint can be supplied with `--endpoint`.

```sh
ollama pull qwen2.5:3b
python lab.py run --model qwen2.5:3b --levels 1 2 3 --seed 101 --seeds 20 --out runs/full
python lab.py replay --run runs/full
python lab.py serve --run runs/full
```

For a quick live check, use `python lab.py run --levels 3 --limit 1 --seeds 1 --out runs/quick`. Use a fresh output directory for a new configuration. Completed masks are checkpointed atomically. Relaunching an interrupted run with identical arguments resumes from those files. If the process was forcibly terminated, verify that its PID has exited before removing its stale `.running` file.

Every constrained LLM arm uses the same fixed-prompt next-token distribution for a given footprint and prefix. The runner queries a distribution only on first use, then reuses its measured values across policies and seeds. The published study required 1,245 backend requests and produced 261,900 sampler proposals, including the uniform control. A proposal is a draw from these cached autoregressive conditionals. Counts of proposals and backend calls therefore measure different costs. The file `scores.json` preserves all three raw per-digit scores. Exact replay from the archive is independent of GPU kernels or server drift.

## Evaluation and files

Validity is the number of legal proposals divided by the number attempted. Uniqueness counts distinct parsed hypotheses divided by attempts. Recovery counts distinct valid ground-truth hypotheses divided by the number of admissible hypotheses. Full-budget experiments cover 9, 36 and 84 distinct top views. Seeds are paired across policies using the same base uniform stream.

| File | Contents |
|---|---|
| `decoder.py` | Prompt, score adapter, policy and validators |
| `lab.py` | Interactive debugger, server and experiment commands |
| `experiment.py` | Checkpoints, paired aggregation and replay |
| `results/reference/traces.jsonl.gz` | Every sampled tuple in order, indexed by mask, seed and policy |
| `results/reference/scores.json` | Full measured digit scores, keyed by mask and prefix |
| `results/reference/run.json` | Checkpoint identity, usage, curves, intervals and example sequences |
| `results/upstream-check.json` | Equivalence checks against the pinned official code |
| `docs/` | Build-free presentation frontend and a copy of the reference report |
| `presentation/` | Editable four-speaker narration and synchronized English captions |

To verify the representation and scores independently, install the pinned upstream evaluator’s Python dependencies and run the audit. It imports the original generator, text parser, structure canonicalizer and evaluation code. All 2,619 distinct voxel completions are checked.

```sh
git clone https://github.com/CTT-Pavilion/_HypoSpace.git ../_HypoSpace
git -C ../_HypoSpace checkout c69e9318577b34b5b896996571aefd4ba6053f58
python -m pip install numpy scipy PyYAML requests networkx
python tools/verify_upstream.py --upstream ../_HypoSpace --traces results/reference/traces.jsonl.gz --out runs-audit.json
python tools/ablate.py
```

Benchmark credit goes to Tingting Chen and coauthors, ICML 2026. [Paper and citation](https://proceedings.mlr.press/v306/chen26bz.html) · [Pinned upstream benchmark](https://github.com/CTT-Pavilion/_HypoSpace/tree/c69e9318577b34b5b896996571aefd4ba6053f58)

