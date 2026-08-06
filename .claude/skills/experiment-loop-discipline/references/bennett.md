# Bennett's razor — the argument behind the specificity criterion

Source: Michael Timothy Bennett, *The Optimal Choice of Hypothesis Is the Weakest, Not the Shortest*, AGI 2023. [arXiv:2301.12987](https://arxiv.org/abs/2301.12987)

Read this when a user asks *why* specificity beats brevity, pushes back on the criterion, or wants the citation. The SKILL.md summary is enough for normal use.

## The setup

Generalisation is framed as: given sets `A ⊂ B`, infer from `A` a hypothesis sufficient to construct `B`. Many hypotheses fit `A`; only some extend to `B`. Which do you pick?

The standard answer is Ockham's razor operationalised as minimum description length — prefer the shortest. Bennett's answer is **weakness**.

Formally, in his enactive-cognition lattice:

- The **extension** of a statement `a` is `Z_a = {b ∈ L_v : a ⊆ b}` — the statements that entail it.
- The **weakness** of `a` is `|Z_a|`, the cardinality of that extension.
- A **model** of a task is a statement whose licensed decisions are all correct ones.
- **Induction** picks `h ∈ argmax_{m ∈ M_α} q_v(m)` — the model maximising the proxy `q_v`.

## The results

- **Propositions 1 and 2**: weakness is both sufficient and necessary to maximise the probability that induction generalises from a child task to its parent. The probability is `2^|Z_S̄α ∩ Z_h| / 2^|Z_S̄α|`, maximised when `|Z_h|` is.
- **Proposition 3**: minimising description length is *neither* necessary nor sufficient, shown by explicit counterexample where the two proxies select different hypotheses.
- **Experiments**: binary addition and multiplication over 8-bit strings (4 bits in, 4 bits out), 75–256 trials per condition. Max-weakness generalised at **110–500%** the rate of MDL, and the average *extent* of generalisation was **103–156%**.

## The razor

> Explanations should be no more specific than necessary.

Contrast with Ockham's "no more complex than necessary." Bennett is explicit that the two are different: *"A simple statement need not be weak, for example 'all things are blue crabs.' Likewise, a complex utterance can assert nothing. Weakness is a consequence of extension, not form."*

## Two limits that matter in practice

**The empty hypothesis is maximally weak.** Footnote 10 notes that `2^|Z_h| / 2^|L_v|` is maximised at `h = ∅` — assume nothing, and you generalise everywhere by asserting nothing. Weakness maximisation is only meaningful *subject to* the hypothesis remaining a model of the observed task.

This is why the skill's Step 4 is scoped to changes that already passed the gate and probe. Written loosely as "prefer the least specific change," an agent can rationalise reverting all work as maximally general — and it will, especially unsupervised at 3am. The sufficiency constraint is not a technicality.

**Uniform task distribution is assumed.** Definition 4 assumes a uniform distribution over tasks, and the Pareto-optimality claim rests on it. Bennett acknowledges directly that "another proxy may perform better given cherry-picked combinations of child and parent task."

Most real projects are cherry-picked in exactly this way — they target one platform, one budget, one workload. So the criterion is a strong default heuristic for work meant to transfer, not a proof about any particular codebase. When a user's goal genuinely is "best result on this specific configuration," specificity to that configuration is correct and the criterion should be applied narrowly, mainly as an anti-noise-fitting device.

## On applying this to neural networks

Section 6 speculates that LLMs may be prone to fabrication "because they are optimised only to minimise loss, rather than maximise weakness," and that grokking might be induced by optimising for weakness. It closes: *"Future research should investigate means by which weakness can be maximised in the context of neural networks."*

Treat that as an open problem, not a recipe. The paper offers no method for computing weakness over a network's parameters, and the extension `|Z_h|` is defined over a finite propositional vocabulary that has no established mapping to continuous weights. This is why the skill applies the idea at the level of a **loop's selection rule** — where hypotheses are discrete, enumerable changes and "how many configurations does this hold across" is directly measurable — rather than as a term in a loss function. If a user proposes a weakness regulariser, that's a research project, and worth saying so.
