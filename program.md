# autoresearch

This is an experiment to have the LLM do its own research.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar5`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. Do not modify.
   - `train.py` — the file you modify. Model architecture, optimizer, training loop.
4. **Verify data exists**: Check that `~/.cache/autoresearch/` contains data shards and a tokenizer. If not, tell the human to run `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Calibrate the noise floor**: Run the unmodified baseline three times at different weight inits:

   ```bash
   for s in 42 1337 2024; do AUTORESEARCH_SEED=$s uv run train.py > run.seed$s.log 2>&1; done
   grep -h "^val_bpb:" run.seed*.log
   ```

   Take the standard deviation of the three val_bpb values and call it `sigma`. Write it down — every accept/reject decision below is measured in units of it. This costs ~15 minutes once and is what makes the rest of the run mean anything. Without it you cannot tell an improvement from a different roll of the dice.
7. **Confirm and go**: Confirm setup looks good and report `sigma` to the human.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on a single GPU. The training script runs for a **fixed time budget of 5 minutes** (wall clock training time, excluding startup/compilation). You launch it simply as: `uv run train.py`.

**What you CAN do:**
- Modify `train.py` — this is the only file you edit. Everything is fair game: model architecture, optimizer, hyperparameters, training loop, batch size, model size, etc.
- Set `AUTORESEARCH_SEED=<n>` to re-run an unchanged `train.py` under a different weight init. Use this for probing (see the experiment loop); do not hardcode a new default seed, and never pick a seed because it happens to flatter a result.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed evaluation, data loading, tokenizer, and training constants (time budget, sequence length, etc).
- Install new packages or add dependencies. You can only use what's already in `pyproject.toml`.
- Modify the evaluation harness. The `evaluate_bpb` function in `prepare.py` is the ground truth metric.

**The goal is simple: get the lowest val_bpb.** Since the time budget is fixed, you don't need to worry about training time — it's always 5 minutes. Everything is fair game: change the architecture, the optimizer, the hyperparameters, the batch size, the model size. The only constraint is that the code runs without crashing and finishes within the time budget.

**VRAM** is a soft constraint. Some increase is acceptable for meaningful val_bpb gains, but it should not blow up dramatically.

**Specificity criterion**: Among changes that *actually improve val_bpb*, prefer the one that is least specific — that constrains the fewest configurations. This is the selection rule, and it is not the same as preferring shorter code.

Read both halves of that sentence together. The improvement requirement comes first and is not negotiable: a change must still fit the evidence. "Change nothing" is maximally unspecific and explains nothing, so reverting to baseline is never justified by this criterion. Only once a change has cleared the bar in the experiment loop below does specificity decide whether to keep it.

Length and specificity come apart most sharply on magic numbers. `MATRIX_LR = 0.0374`, tuned to four decimals against a single run, is one line but holds at exactly one point in configuration space; it will not survive a change of seed or depth. A longer rule deriving the same quantity from something structural — scaling an LR with model width, setting a warmup fraction from step count — commits to less and holds across more. Given both options, take the less specific one even though it is more code.

Simplicity still matters, but for a different reason: `train.py` has to stay readable and reviewable by a human. Treat that as a tiebreaker on style, not as evidence a change will generalize. Removing something and getting equal or better results is still a great outcome — a genuine win on both counts.

The background is Bennett, [*The Optimal Choice of Hypothesis Is the Weakest, Not the Shortest*](https://arxiv.org/abs/2301.12987) (AGI 2023), which proves that when many hypotheses fit the data, minimizing description length is neither necessary nor sufficient for picking the one that generalizes; the necessary and sufficient proxy is *weakness*, the size of the hypothesis's extension. A simple statement need not be a weak one — Bennett's example is "all things are blue crabs", which is short and wildly specific. Hence his razor: **explanations should be no more specific than necessary.**

**The first run**: Your very first run should always be to establish the baseline, so you will run the training script as is.

## Output format

Once the script finishes it prints a summary like this:

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

Note that the script is configured to always stop after 5 minutes, so depending on the computing platform of this computer the numbers might look different. You can extract the key metric from the log file:

```
grep "^val_bpb:" run.log
```

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions).

The TSV has a header row and 7 columns:

```
commit	val_bpb	memory_gb	status	seeds	scope	description
```

1. git commit hash (short, 7 chars)
2. val_bpb achieved at seed 42 (e.g. 1.234567) — use 0.000000 for crashes
3. peak memory in GB, round to .1f (e.g. 12.3 — divide peak_vram_mb by 1024) — use 0.0 for crashes
4. status: `keep`, `discard`, `noise`, or `crash`. Use `noise` when `delta < sigma` and `discard` when the change was a candidate but failed the probe — the distinction tells you later whether an idea was untested or actually tested and rejected
5. seeds: how many of the probed inits improved on baseline, as `k/n` (e.g. `3/3`, `1/3`). Use `1/1` for changes that never reached the probe
6. scope: the widest claim the evidence supports — `seed-42-only`, `all-seeds`, or `all-seeds+depth` if you also probed depth
7. short text description of what this experiment tried

Example:

```
commit	val_bpb	memory_gb	status	seeds	scope	description
a1b2c3d	0.997900	44.0	keep	3/3	all-seeds	baseline
b2c3d4e	0.993200	44.2	keep	3/3	all-seeds	scale matrix LR with model width
c3d4e5f	0.996100	44.0	discard	1/3	seed-42-only	hand-tuned matrix LR 0.0374
d4e5f6g	0.997500	44.0	noise	1/1	seed-42-only	switch to GeLU activation
e5f6g7h	0.000000	0.0	crash	0/0	-	double model width (OOM)
```

Rows 3 and 4 are the two failure modes the loop is built to catch. `c3d4e5f` posted a real-looking gain that existed only at one init; `d4e5f6g` moved val_bpb by less than `sigma`, which is no evidence at all.

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar5` or `autoresearch/mar5-gpu0`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Tune `train.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
5. Read out the results: `grep "^val_bpb:\|^peak_vram_mb:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix. If you can't get things to work after more than a few attempts, give up.
7. Compute `delta` = (reference val_bpb at seed 42) − (this run's val_bpb). Positive means improvement. The *reference triple* is the three val_bpb values of whatever is currently at the tip of the branch — initially the three baseline runs from setup step 6.
8. Apply the accept rule:
   - **`delta < sigma`** → status `noise`. This is indistinguishable from a different roll of the dice. Do not keep it because it "looks directionally right" — most changes land here, and accepting them is how the branch fills up with things that do nothing.
   - **`delta >= sigma`** → this is a *candidate*, not a keep. Probe it before deciding.
9. **Weakness probe.** Re-run the candidate unchanged at two more inits: `AUTORESEARCH_SEED=1337` and `AUTORESEARCH_SEED=2024`. You now have three val_bpb values for the change, against the three in the reference triple.
   - Keep if the change beats the reference at **all three** seeds, or at two of three *and* the mean improvement across all three still exceeds `sigma`.
   - Otherwise status `discard`. A change that wins big at seed 42 and loses at the other two is an artifact of one draw at initialization, not a result.
10. Record the outcome in the tsv (NOTE: do not commit the results.tsv file, leave it untracked by git)
11. If the change was kept, "advance" the branch keeping the git commit, **and its three probe values become the new reference triple** — you already paid for them, so carry them forward rather than re-running. Otherwise `git reset` back to where you started and leave the reference triple alone.

`sigma` itself stays fixed at the value measured during setup. It estimates the noise of this platform, not of any particular commit, so there is no need to recompute it as the branch advances.

**Why the probe.** The dataloader in `prepare.py` is deterministic, so a fixed seed means every experiment is a single draw from one weight init. A one-run accept rule therefore selects for changes that suit *that specific init* — the strongest, most specific hypothesis consistent with the evidence, which is exactly the wrong end of the specificity criterion. The probe is a cheap measurement of how many configurations a change actually holds across.

**What the probe costs.** Two extra runs per candidate. If roughly a third of experiments become candidates, throughput drops from ~12 ideas/hour to ~7. That is the intended trade: fewer ideas tested, but the ones on the branch at the end are real. Do not skip the probe to get the number back up.

**Probing beyond the seed.** The seed probe is mandatory because init variance is pure noise and overfitting to it is never correct. Probing other dimensions — `DEPTH ± 2`, LR × 2 — is optional and costs more runs, so reserve it for changes you believe are structural rather than tuned. Note that these probes are not free of judgment the way the seed probe is: this repo's stated goal is the best model for *this* platform at *this* time budget, so some specificity to the fixed configuration is legitimately correct. Probe depth and LR when you want a change to transfer beyond this box; skip it when you're deliberately tuning for the box.

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate. If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever).

**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for startup and eval overhead). If a run exceeds 10 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (OOM, or a bug, or etc.), use your judgment: If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — read papers referenced in the code, re-read the in-scope files for new angles, try combining previous near-misses, try more radical architectural changes. The loop runs until the human interrupts you, period.

As an example use case, a user might leave you running while they sleep. If each experiment takes you ~5 minutes then you can run approx 12/hour, for a total of about 100 over the duration of the average human sleep. The user then wakes up to experimental results, all completed by you while they slept!
