#!/usr/bin/env python3
"""Noise-floor calibration and accept-rule arithmetic for experiment loops.

Stdlib only, so it runs anywhere without setup.

    loopstat.py calibrate 0.9979 0.9994 0.9961
    loopstat.py decide --sigma 0.0016 \
        --reference 0.9979 0.9994 0.9961 --candidate 0.9931 0.9948 0.9925

Both subcommands take --higher-better for metrics where up is good
(accuracy, tokens/sec); the default assumes lower is better (loss, latency).
Add --json for machine-readable output.
"""

import argparse
import json
import statistics
import sys


def calibrate(values, higher_better):
    if len(values) < 2:
        raise ValueError("need at least 2 baseline runs to estimate spread")
    sigma = statistics.stdev(values)  # sample stddev (n-1)
    mean = statistics.fmean(values)
    return {
        "n": len(values),
        "mean": mean,
        "sigma": sigma,
        "spread": max(values) - min(values),
        "relative_sigma": (sigma / abs(mean)) if mean else None,
        "direction": "higher is better" if higher_better else "lower is better",
        "values": values,
    }


def _gain(reference, candidate, higher_better):
    """Positive means the candidate is an improvement."""
    return candidate - reference if higher_better else reference - candidate


def decide(reference, candidate, sigma, higher_better):
    if sigma <= 0:
        raise ValueError(
            "sigma must be positive; a deterministic metric needs no gate "
            "(see Step 0 of the skill)"
        )
    if not reference or not candidate:
        raise ValueError("need at least one reference and one candidate value")

    # Stage 1 gates on the primary run: first candidate vs first reference.
    primary_delta = _gain(reference[0], candidate[0], higher_better)
    if primary_delta < sigma:
        return {
            "verdict": "noise",
            "status": "noise",
            "reason": (
                f"primary delta {primary_delta:.6g} is below sigma {sigma:.6g}; "
                "indistinguishable from run-to-run variation"
            ),
            "primary_delta": primary_delta,
            "probed": 0,
            "wins": 0,
            "mean_delta": None,
        }

    # Stage 2 probes across the nuisance dimension. Compare pairwise over the
    # values both sides share; unmatched trailing runs are ignored rather than
    # silently compared against a different draw.
    n = min(len(reference), len(candidate))
    deltas = [_gain(reference[i], candidate[i], higher_better) for i in range(n)]
    wins = sum(1 for d in deltas if d > 0)
    mean_delta = statistics.fmean(deltas)

    if n == 1:
        verdict, status = "candidate", "unprobed"
        reason = (
            f"cleared the gate (delta {primary_delta:.6g} >= sigma {sigma:.6g}) "
            "but has only one run; probe it at 2 more nuisance values before keeping"
        )
    elif wins == n:
        verdict, status = "keep", "keep"
        reason = f"improved at all {n}/{n} probed values (mean delta {mean_delta:.6g})"
    elif wins >= 2 and mean_delta > sigma:
        verdict, status = "keep", "keep"
        reason = (
            f"improved at {wins}/{n} probed values and mean delta "
            f"{mean_delta:.6g} exceeds sigma {sigma:.6g}"
        )
    else:
        verdict, status = "discard", "discard"
        reason = (
            f"improved at only {wins}/{n} probed values with mean delta "
            f"{mean_delta:.6g}; the initial gain looks like an artifact of one draw"
        )

    return {
        "verdict": verdict,
        "status": status,
        "reason": reason,
        "primary_delta": primary_delta,
        "probed": n,
        "wins": wins,
        "mean_delta": mean_delta,
        "scope_hint": f"{wins}/{n}",
        "per_run_deltas": deltas,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calibrate", help="estimate sigma from repeated baseline runs")
    c.add_argument("values", type=float, nargs="+", help="baseline metric values")
    c.add_argument("--higher-better", action="store_true")
    c.add_argument("--json", action="store_true")

    d = sub.add_parser("decide", help="apply the two-stage accept rule")
    d.add_argument("--sigma", type=float, required=True)
    d.add_argument("--reference", type=float, nargs="+", required=True)
    d.add_argument("--candidate", type=float, nargs="+", required=True)
    d.add_argument("--higher-better", action="store_true")
    d.add_argument("--json", action="store_true")

    a = p.parse_args()

    try:
        if a.cmd == "calibrate":
            r = calibrate(a.values, a.higher_better)
            if a.json:
                print(json.dumps(r, indent=2))
            else:
                print(f"n           {r['n']}")
                print(f"mean        {r['mean']:.6g}")
                print(f"sigma       {r['sigma']:.6g}")
                print(f"spread      {r['spread']:.6g}  (max - min)")
                if r["relative_sigma"] is not None:
                    print(f"relative    {r['relative_sigma']:.2%} of mean")
                print(f"direction   {r['direction']}")
                print()
                print(f"Gate: a change must move the metric by more than {r['sigma']:.6g}")
                print("to be worth probing. Anything smaller is noise.")
        else:
            r = decide(a.reference, a.candidate, a.sigma, a.higher_better)
            if a.json:
                print(json.dumps(r, indent=2))
            else:
                print(f"verdict     {r['verdict'].upper()}")
                print(f"status      {r['status']}")
                print(f"reason      {r['reason']}")
                if r["probed"]:
                    print(f"probed      {r['wins']}/{r['probed']} improved")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
