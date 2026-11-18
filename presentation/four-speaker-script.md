# Four-speaker presentation script

Ten-minute English presentation. Each chapter uses a distinct synthesized voice. The four roles can be assigned to team members for a live recording.

## Speaker 1 · The benchmark · 00:00–02:30

### 00:00 · How many explanations can one model find?

Look at this structure from directly above. Three squares are occupied. Can you tell which stack is tallest? You could guess, but the top view would look exactly the same if the heights changed. A language model can therefore give a perfectly defensible answer and still miss most of the possibilities. Our project asks how many different valid structures a frozen language model can discover when it has a fixed number of attempts. We test that question on the voxel reconstruction task in HypoSpace, introduced by Chen and colleagues.

### 00:35 · One observation, 27 possible worlds

Start with a three by three grid. A colored square means at least one cube lies in that column. An empty square means zero. Gravity gives us a convenient description. Every occupied column is a solid stack, with no floating blocks. Read the occupied positions in row order. Each one can have height one, two, or three, independently of the others. Multiplying those choices gives twenty-seven distinct structures for this observation. Each has exactly the same footprint.

### 01:11 · Three ways to score a sequence

Suppose four draws give the three stacks shown here, with the first answer occurring twice. Every proposed structure is legal. Validity is four out of four. Uniqueness counts three distinct proposals out of four attempts, so it reaches seventy-five percent. Recovery uses a different denominator. Three distinct valid structures cover only three of the twenty-seven possible structures. This example shows why we track recovery through time. The second copy consumes a draw and leaves the set of discoveries unchanged.

### 01:48 · Why more draws can still miss answers

Imagine choosing among all twenty-seven answers uniformly and independently. One particular answer is missed with probability twenty-six over twenty-seven on a single draw. Raise that probability to the twenty-seventh power to miss it every time. Subtracting from one gives the expected fraction recovered, about sixty-four percent. Even this generous reference leaves many answers unseen. If the model concentrates probability on a few familiar patterns, independent draws revisit those patterns even more often. The second speaker will show how earlier proposals can change the next draw.

## Speaker 2 · The decoder · 02:30–05:00

### 02:30 · A compact output space for the model

Our decoding experiment gives every method the same compact interface. The model sees the observation and proposes one height for each occupied cell. For example, two, one, three represents a two-cube stack in the first cell, a single cube in the second, and three cubes in the last. Each chosen digit comes from the legal height alphabet. Expanding these digits into layers gives a complete structure that can be scored against the observation. This representation makes it possible to study repeated answers while holding output formatting fixed.

### 03:07 · A count depends on the path so far

Consider three earlier proposals. Two of them ended in one after the prefix two, one. The third ended in three after the same prefix. If the next proposal starts with two, one, those counts tell us exactly which endings have already attracted probability. A single count per position would mix this history together with proposals that started differently. The prefix table keeps those cases separate. It is small enough to inspect, and it changes as the model draws more structures.

### 03:38 · Use history to rebalance the next choice

At a decision point, we subtract a penalty from each model log probability. The penalty grows as the logarithm of one plus the visit count. Its scale depends on the gap between the model's largest and smallest height scores. That lets one previous visit counter a sharp local preference. Normalizing the adjusted scores gives a new probability distribution over the three possible heights. The decoder then samples, advances one position, and eventually records the finished proposal. Drawing a duplicate still spends one attempt. Only the proposals seen for this observation enter its history. The strategy never needs a catalog of all the answers.

### 04:22 · What each comparison controls

The model-only baseline measures what the shared interface can do on its own. Complexity stratification builds on the paper's idea of distributing attention across structures of different sizes. For stacks, size is the total number of cubes. A position-only count provides a closer comparison. It can encourage every height at every position while still overlooking combinations between positions. The conditional version remembers which earlier choices led to the current position. Comparing these alternatives helps identify what information in the history actually helps.

## Speaker 3 · The experiment · 05:00–07:30

### 05:00 · A budget of one draw per possible answer

Our third section describes the paired experiment. We used Qwen two point five, three billion parameters on a server with an RTX forty eighty Super graphics card. Across three difficulty levels we evaluated all one hundred twenty-nine possible footprints with one, two, or three occupied cells. The hardest level uses 84 three-column layouts and 20 decoding seeds per layout in the hardest setting. Every method receives the same observation, the same alphabet, and the same budget of twenty-seven proposals in a hard-level run. Each proposal corresponds to a complete set of column heights. When a sampled structure repeats, it remains in the trace and counts towards that total. This lets us compare coverage at each draw as well as after the final draw.

### 05:46 · How much of the space was recovered?

At the end of twenty-seven draws, unmodified model sampling recovered 19.7 percent of the valid structures on average. Prefix feedback reached 79.7 percent. That is a paired difference of 59.9 percentage points across the same layouts and seeds. The seed-panel bootstrap interval for that difference runs from 59.7 to 60.2 points, conditional on these layouts. All methods produce legal vectors here. The change in recovery therefore comes from finding different structures within the fixed number of attempts.

### 06:21 · Follow the discoveries through time

The horizontal axis counts complete proposals. The vertical axis shows the mean fraction of valid structures recovered by that point. After nine draws, the baseline has recovered 13.0 percent and the prefix method has recovered 33.0 percent. At eighteen draws, the corresponding values are 17.1 and 61.0 percent. A curve starts to flatten when repeats consume more of the new draws. Comparing the curves at the same point keeps the query budget fixed.

### 06:52 · Which part of memory matters?

The marginal-count variant recovers 45.8 percent on this setting. Restricting the counts to the actual path raises recovery to 79.7 percent. That gap measures the value of conditioning the feedback on earlier digits, with the model and the strength rule held fixed. The complexity-stratified decoder reaches 44.2 percent. It allocates the exact histogram of total cube counts, although layouts inside a single size group can still repeat. The easiest level reverses their order. With one occupied cell, stratification recovers every height, while prefix feedback recovers 87.8 percent.

## Speaker 4 · The workbench · 07:30–10:00

### 07:30 · Debug an individual proposal

In the terminal, the inspect command selects the observation, policy, and draw number. This example stops after four proposals and lists every sampled height vector in order. The recovery counter is cumulative. A line marked new adds one structure to the set. A repeated vector leaves that counter where it was. For the selected draw, the detailed trace reports the partial prefix, the original log probabilities, the visit counts, and the final sampling probabilities. That is enough information to see exactly why a previously frequent digit lost weight.

### 08:06 · Replay the same run in the browser

The browser replays the archived experiment. Select a footprint to fix the observation, choose a decoder, and follow one proposal at a time. The stack diagram turns the numeric heights back into cubes, so you can see what each new vector means in three dimensions. Compare the structures with their common footprint. Their appearance from above remains the same even as the heights change. The terminal and the presentation view use the same measured run. The interactive display can run locally from the saved results.

### 08:39 · What do the model’s preferences contribute?

An additional ablation changes how we interpret the gain. Give all three heights equal starting scores, while keeping the model's original score spread to calibrate the visit penalty. Recovery rises to ninety-four point four percent, above the full prefix policy's seventy-nine point seven percent. Flattening both the scores and their spread gives seventy-four point eight percent. On this task, calibration helps, and the model's height preferences can cost coverage. Validity is built into the representation, and exact enumeration is possible. Whether these effects transfer to other domains remains an open question.

### 09:19 · The experiment, from prompt to playback

The project connects three pieces. A frozen model supplies local preferences. An online memory records the choices made along each sampled path. A deterministic score turns the resulting sequence into a coverage curve. You can inspect the individual draws, reproduce the comparisons, and replay the measurements in the browser using the public repository shown here. In the tested three-column setting, the prefix decoder increased mean recovery by 59.9 points over the frozen-model sampling baseline. The original benchmark and its authors' implementation are linked in the repository. Thank you for watching.

## Sources

Benchmark design, voxel rules and metric definitions follow Chen et al. [HypoSpace, ICML 2026](https://proceedings.mlr.press/v306/chen26bz.html).

The experiment uses the frozen model, decoding arms, runs and measurements documented in the [public project repository](https://github.com/Nek0laos/hypospace-coverage-lab).

The four synthetic narration roles use a local multi-speaker voice model. [Piper LibriTTS voice model](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/libritts/high).
