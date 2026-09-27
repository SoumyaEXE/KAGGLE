"""Replication chart: the same scorecard from two independent runs of the same rows.

    python compare_runs.py [--a figures/round1/scorecard.json] [--b figures/rerun/scorecard.json]
                           [--out figures/rerun/fig14_replication.png]

Models present in both runs get a dumbbell (run A hollow, run B filled, each with its
story-bootstrap 95% interval). Prints per-model shifts and the Spearman rank correlation.
"""
import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analyze_round1 as A


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="figures/round1/scorecard.json")
    ap.add_argument("--b", default="figures/rerun/scorecard.json")
    ap.add_argument("--label-a", default="Round 1 (2026-09-26)")
    ap.add_argument("--label-b", default="Kaggle rerun (2026-09-27)")
    ap.add_argument("--out", default="figures/rerun/fig14_replication.png")
    a = ap.parse_args()
    ra = {t["model"]: t for t in json.load(open(a.a, encoding="utf-8"))["table"]}
    rb = {t["model"]: t for t in json.load(open(a.b, encoding="utf-8"))["table"]}
    both = sorted(set(ra) & set(rb), key=lambda m: (ra[m]["overall"] + rb[m]["overall"]) / 2)
    rho = spearman([ra[m]["overall"] for m in both], [rb[m]["overall"] for m in both])
    for m in both[::-1]:
        print(f"{m:<18} {ra[m]['overall']:5.1f} -> {rb[m]['overall']:5.1f}  ({rb[m]['overall'] - ra[m]['overall']:+.1f})"
              f"  rank {ra[m]['rank']} -> {rb[m]['rank']}")
    print(f"spearman rho = {rho:.3f} over {len(both)} models")

    A.style()
    fig, ax = plt.subplots(figsize=(10.4, 0.62 * len(both) + 2.0))
    off = 0.14
    for i, m in enumerate(both):
        pa, pb = ra[m], rb[m]
        ax.plot([pa["overall"], pb["overall"]], [i, i], color=A.STONE, lw=1.0, zorder=1)
        for p, dy, filled in ((pa, off, False), (pb, -off, True)):
            lo, hi = p["ci"]["overall"]
            ax.plot([lo, hi], [i + dy, i + dy], color=A.BLUE, lw=1.6, alpha=0.35 if not filled else 0.6,
                    solid_capstyle="round")
            ax.scatter([p["overall"]], [i + dy], s=58, zorder=3, color=A.BLUE if filled else A.SURFACE,
                       edgecolor=A.BLUE, linewidth=1.6)
        d = pb["overall"] - pa["overall"]
        ax.text(103, i, f"{d:+.0f}", va="center", ha="left", fontsize=10,
                color=A.INK if abs(d) >= 10 else A.MUTED, fontweight="bold" if abs(d) >= 10 else "normal")
    ax.text(103, len(both) - 0.4, "change", fontsize=9, color=A.MUTED, ha="left", va="bottom")
    ax.set_yticks(range(len(both)), both)
    ax.tick_params(axis="y", length=0, labelsize=10.5, labelcolor=A.INK)
    ax.set_xlim(-2, 102)
    ax.set_ylim(-0.6, len(both) - 0.1)
    ax.set_xlabel("Overall scorecard score (0–100)")
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.scatter([], [], s=58, color=A.SURFACE, edgecolor=A.BLUE, linewidth=1.6, label=a.label_a)
    ax.scatter([], [], s=58, color=A.BLUE, label=a.label_b)
    ax.legend(loc="lower right", frameon=False, fontsize=9.5)
    A.SOURCE = "Source: Is This Still the Test?, same 96 rows asked twice on Kaggle Benchmarks. "
    A.finish(fig, ax, "Same questions, asked again: does the ranking hold?",
             f"Overall score in two independent runs; lines = story-bootstrap 95% intervals. "
             f"Rank correlation between runs: Spearman ρ = {rho:.2f} ({len(both)} models).",
             a.out, ci=False)


if __name__ == "__main__":
    main()
