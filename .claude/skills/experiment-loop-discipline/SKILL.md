---
name: experiment-loop-discipline
description: Measurement discipline for experiment loops that keep or discard changes based on a metric. Use whenever the user is building, fixing, auditing, or running a propose → measure → keep-or-discard cycle — overnight agent research loops, benchmark-driven tuning, prompt or eval optimization, hyperparameter sweeps, recursive self-improvement loops. Trigger especially when they ask whether an improvement is real, why their loop accumulates changes that don't help, how to separate signal from run-to-run noise, how to stop overfitting to one seed or one run, or when they show you a loop's accept rule, keep/discard criterion, or results log. Also trigger on "is this gain real", "my agent keeps keeping things that do nothing", or a request to review an autonomous optimization setup. Do NOT use for one-off statistical tests unconnected to an iterative loop, or for ordinary A/B test analysis on user traffic.
---

# Experiment loop discipline

## The failure this prevents

A loop proposes a change, measures a metric, and keeps the change if the metric improved. Run it overnight and you wake up to a branch full of changes, most of which do nothing.

The reason is almost always the same: **the loop never measured its own noise, so it cannot tell a real gain from a different roll of the dice.** If run-to-run variation is ±0.004 and the accept rule is "keep anything better," then roughly half of everything kept is noise. Worse, the loop is actively selecting *for* changes that happen to suit whatever was held fixed — one seed, one machine state, one sampling order. Those changes look like discoveries and are artifacts.

Your job is to install four things: a measured noise floor, a gate that uses it, a probe that tests candidates across the thing being held fixed, and a selection rule that prefers less-specific changes. Adapt each to the loop in front of you — the mechanisms are general, the numbers never are.

## Step 0 — triage: does this loop have noise at all?

Ask what the metric is and whether re-running the *unchanged* baseline twice gives the same number.

**If the metric is deterministic** — type errors, bundle size, a hermetic test suite, line counts, a fixed-input diff — then σ = 0, the gate is vacuous, and probing costs 3x for nothing. Say so plainly and stop early. Only the specificity criterion (Step 4) still applies, and there it's a judgment call rather than a measurement. Telling someone they don't need the machinery is a real outcome; installing it anyway is how this pattern gets discredited.

**If the metric varies** across identical runs, continue. Most interesting loops are here: anything involving model training, LLM sampling, wall-clock timing, or concurrent execution.

## Step 1 — name the metric and the nuisance dimension

Two questions, and you need both answered before anything else is worth doing.

**What's the metric?** One number, direction stated (lower better / higher better). If the loop optimizes several, ask which one decides keep-vs-discard. A loop with an ambiguous objective has a bigger problem than noise.

**What's the nuisance dimension?** This is the one people miss. It's the thing your loop currently holds fixed but should not be selecting on — the axis you want your results to be invariant across. Common cases:

| Loop | Metric | Nuisance dimension |
|---|---|---|
| Model training / architecture search | val loss, bpb, accuracy | weight init seed, data order |
| LLM eval or prompt optimization | eval score, judge rating | sampling seed, few-shot order, judge model |
| Latency / throughput benchmarking | ms, tokens/sec | machine state, cache warmth, run order |
| Agentic SWE loop with flaky tests | tests passing | test ordering, timing, parallelism |
| Hyperparameter search | held-out score | data split, init |

Find it by asking: *what would change the metric if I changed nothing else?* Then check whether the loop currently varies it. Usually it doesn't — a hardcoded seed, a single benchmark run, one fixed split. That's the leak.

Be precise about what the probe will and won't cover. If a training loop hardcodes a seed but the dataloader is also deterministic, varying the seed tests weight init only, not data order — say that rather than claiming you've covered "run-to-run variance." Overstating a probe's reach is worse than a narrow probe honestly labeled.

## Step 2 — calibrate the noise floor

Run the **unchanged** baseline 3–5 times, varying only the nuisance dimension. Take the sample standard deviation. Call it `sigma`.

```bash
python ~/.claude/skills/experiment-loop-discipline/scripts/loopstat.py \
  calibrate 0.9979 0.9994 0.9961
```

Cite that full path, not the bare relative `scripts/loopstat.py` — a relative path resolves against the user's working directory, not this skill's, so it will not run for them. If the accept rule is going into a loop that runs unattended, copy `loopstat.py` into their repo instead, so the loop doesn't depend on the skill being installed.

This costs a few runs once, and it is what makes every later decision mean anything. Resist the urge to skip it and eyeball a threshold — people consistently guess low, which is precisely the error that lets noise through.

Report `sigma` to the user in the metric's own units and in context: "run-to-run spread is ±0.0016, so a change needs to move val_bpb by more than that before it's worth investigating." If `sigma` comes back large enough that plausible improvements can't clear it, that's important information about the loop's resolution — surface it rather than quietly lowering the bar. The honest options are more baseline runs, a longer run per experiment, or accepting that only large effects are detectable.

`sigma` estimates the platform's noise, not any particular change's, so it stays fixed as the loop advances. No need to recompute.

## Step 3 — the two-stage accept rule

Replace "keep if the metric improved" with:

**Stage 1 — gate.** Compute `delta` = reference metric − candidate metric (sign it so positive means improvement). If `delta < sigma`, this is noise. Discard, and log it as *untested* rather than *rejected* — the distinction matters later when someone asks whether an idea was ever really tried.

**Stage 2 — probe.** If `delta >= sigma`, you have a *candidate*, not a keep. Re-run it unchanged at two more values of the nuisance dimension. Keep it if it beats the reference at all three, or at two of three with mean improvement still above `sigma`. Otherwise discard.

```bash
python ~/.claude/skills/experiment-loop-discipline/scripts/loopstat.py \
  decide --sigma 0.0016 \
  --reference 0.9979 0.9994 0.9961 --candidate 0.9931 0.9948 0.9925
```

A change that wins big on the first run and loses on the other two is an artifact of one draw, not a result. This is the single highest-value thing the skill does, because that pattern is indistinguishable from a discovery when you only look at one run.

**Carry the reference forward.** When a change is kept, its three probe values become the new reference — you already paid for them. Comparing later candidates against a stale baseline silently re-introduces the bug you just fixed, and it's an easy mistake to make when the loop runs for hours.

**Account for the cost out loud.** Two extra runs per candidate. If roughly a third of experiments become candidates, throughput drops about 40% — e.g. 12 ideas/hour to 7. State this in whatever instructions you write, so the agent running the loop understands the trade and doesn't optimize it away at 3am. Fewer ideas tested, but the survivors are real.

## Step 4 — select by specificity, not brevity

Among changes that *actually pass Step 3*, prefer the one that constrains the fewest configurations.

Read both halves of that together. The improvement requirement comes first: a change must still fit the evidence. "Change nothing" constrains nothing at all and explains nothing, so reverting to baseline is never justified by this criterion. Specificity only breaks ties among changes that already earned their place.

The rule matters because it contradicts the instinct most loops encode, which is *prefer simpler / shorter*. Those come apart hardest on magic numbers:

- `LEARNING_RATE = 0.0374`, tuned to four decimals against one run, is **one line** but holds at exactly one point in configuration space. It will not survive a change of seed or scale.
- A ten-line rule deriving that quantity from something structural — scaling with model width, setting a warmup fraction from step count — is **longer** but commits to less and holds across more.

Take the second one. Brevity is worth keeping as a readability tiebreaker, since humans still have to review the code, but treat it as a style preference and not as evidence a change will generalize.

The underlying argument is Bennett's (see `references/bennett.md` for the formal result and its limits): when many hypotheses fit the data, minimizing description length is neither necessary nor sufficient for picking the one that generalizes. A short statement can be wildly specific — his example is "all things are blue crabs."

Two honest limits to carry with the rule:

- **Steps 1–3 are measurement discipline and stand on their own.** Step 4 is where a theoretical argument is doing work, and its optimality result assumes uniformly distributed tasks — which most real projects violate. Present it as a strong default heuristic, not a theorem about the user's codebase.
- **Some specificity is legitimately correct.** If the loop's stated goal is the best result on *this* machine at *this* budget, tuning to that configuration is the point. Probing the nuisance dimension is always right (noise is never worth fitting); probing *scale* dimensions like model size or budget is a judgment call about whether the user wants transfer beyond their box. Ask rather than assume.

## Step 5 — write it into the loop's own instructions

The discipline only survives if it lives where the loop reads from — `program.md`, `CLAUDE.md`, the agent prompt, the CI config, whatever drives the iteration. Leaving it in chat means it's gone by the second hour.

Produce concretely:

1. A **calibration step** in the loop's setup, with the actual command.
2. The **accept rule**, in the loop's own vocabulary and metric.
3. A **results schema** that records enough to audit decisions later.

For the results log, these columns pull their weight — adapt the names to whatever table already exists:

| Column | Why |
|---|---|
| identifier (commit, run id) | trace back to the change |
| metric value | the primary observation |
| status | `keep` / `discard` / `noise` / `crash` — separating `noise` (never cleared the gate) from `discard` (probed and rejected) tells you whether an idea was tested or merely tried |
| probe result as `k/n` | how many nuisance values improved |
| scope | the widest claim the evidence supports, e.g. `seed-42-only`, `all-seeds`, `all-seeds+scale` |
| description | what was tried |

The `scope` column is what makes the specificity criterion auditable instead of aspirational. Without it, nobody can tell later whether a kept change was ever shown to hold anywhere beyond the run that produced it.

## Adapting rather than transplanting

Everything above is a shape, not a script. A loop measuring p95 latency across machine states needs the same four mechanisms as one measuring validation loss across seeds, and almost none of the same specifics. Signs you're transplanting instead of adapting: you're carrying over seed values from an example, proposing three probe runs when the metric takes an hour each, or installing a gate on a metric that doesn't vary. Read the actual loop first, then fit the mechanisms to it.
