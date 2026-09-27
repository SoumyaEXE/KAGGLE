"""Model scorecard, re-run after every round: several sub-benchmarks per model + an overall rank.

    python scorecard.py [--in results/round1/all_runs_raw.csv] [--out figures/round1] [--round 1]

Writes <out>/fig12_scorecard.png (benchmark table), <out>/fig13_leaderboard.png (overall with
story-bootstrap 95% CIs and P(rank 1)), <out>/scorecard.json and <out>/scorecard.md.
Metric definitions live in scorecard_core.py (shared verbatim with the Kaggle scorecard task).
"""
import argparse
import json
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

import analyze_round1 as A
import scorecard_core as S

N_ROWS = 96
DRAWS = 2000
# failures known from run logs but absent from the CSV (Opus 5's v6 run wrote no decisions file)
DNF_NOTE = {"Claude Opus 5": "quota (403), then empty replies",
            "Qwen3 Next 80B Thinking": "95/96 answered, 1 empty reply (Kaggle does not score partial runs)"}
SCORE_CMAP = A.SEQ_COOL


def model_rows(v):
    cols = ["story", "cond", "action", "reason"]
    return {m: S.prepare(g[cols].to_dict("records")) for m, g in v.groupby("label")}


def build(d, round_no):
    v = d[d.valid]
    n_valid = v.groupby("label").size()
    complete = sorted(n_valid[n_valid == N_ROWS].index)
    rows = model_rows(v[v.label.isin(complete)])
    point = {m: S.subscores(r) for m, r in rows.items()}
    boot = S.bootstrap(rows, draws=DRAWS)

    wins = {m: 0.0 for m in complete}
    for i in range(DRAWS):
        scores = {m: boot[m][i]["overall"] for m in complete}
        top = max(scores.values())
        leaders = [m for m, s in scores.items() if s == top]
        for m in leaders:
            wins[m] += 1 / len(leaders)

    keys = [k for k, _, _ in S.BENCHMARKS] + ["overall"]
    table = []
    for m in complete:
        g = v[v.label == m]
        ci = {k: S.interval([b[k] for b in boot[m]]) for k in keys}
        table.append({
            "model": m, **{k: point[m][k] for k in keys},
            "ci": {k: list(ci[k]) for k in keys},
            "p_first": wins[m] / DRAWS,
            "completion": len(g) / N_ROWS,
            "usd_per_1k": float(g.cost_nanodollars.sum()) / 1e9 / len(g) * 1000,
        })
    table.sort(key=lambda t: -t["overall"])
    for i, t in enumerate(table, 1):
        t["rank"] = i

    # does the winner depend on which sub-benchmarks are averaged?
    avg_keys = [k for k, _, avg in S.BENCHMARKS if avg]
    sensitivity = {}
    for drop in avg_keys:
        keep = [k for k in avg_keys if k != drop]
        order = sorted(table, key=lambda t: -sum(t[k] for k in keep) / len(keep))
        sensitivity[f"without {drop}"] = [t["model"] for t in order]
    # equal-weight alternatives with 2 of 3 benchmarks
    pairs = {f"{a}+{b}": max(table, key=lambda t: t[a] + t[b])["model"]
             for a, b in combinations(avg_keys, 2)}

    dnf = []
    for m in sorted(set(d.label) - set(complete)):
        g = d[d.label == m]
        bad = g[~g.valid].fail.value_counts()
        dnf.append({"model": m, "valid": int(g.valid.sum()), "of": N_ROWS,
                    "why": DNF_NOTE.get(m) or (bad.index[0] if len(bad) else "incomplete")})
    return {"round": round_no, "draws": DRAWS, "benchmarks": [
        {"key": k, "label": lab, "in_overall": avg} for k, lab, avg in S.BENCHMARKS],
        "table": table, "dnf": dnf, "rank_without_one": sensitivity, "leader_by_pair": pairs}


def _fmt(x, pct=False):
    return "–" if x is None else f"{x:.0f}"


def fig_scorecard(res, out):
    tab, dnf = res["table"], res["dnf"]
    cols = [("overall", "Overall"), ("boundary", "Boundary\nhold"), ("detection", "Reality\ndetection"),
            ("escalation", "Escalation"), ("uptake", "Instruction\nuptake")]
    nrow = len(tab) + len(dnf)
    fig, ax = plt.subplots(figsize=(11.2, 1.5 + 0.46 * nrow + 0.9))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(nrow + 0.4, -1.25)
    ax.axis("off")
    x_rank, x_model, x0, w = 0.25, 0.6, 2.75, 1.15
    x_comp, x_cost = x0 + w * len(cols) + 0.3, x0 + w * len(cols) + 1.45
    head_y = -0.62
    ax.text(x_rank, head_y, "#", color=A.MUTED, fontsize=9, va="center")
    ax.text(x_model, head_y, "Model", color=A.MUTED, fontsize=9, va="center")
    for j, (_, lab) in enumerate(cols):
        ax.text(x0 + w * j + w / 2, head_y, lab, color=A.INK if j == 0 else A.MUTED, fontsize=9,
                ha="center", va="center", fontweight="semibold" if j == 0 else "normal")
    ax.text(x_comp + 0.5, head_y, "Valid\nrows", color=A.MUTED, fontsize=9, ha="center", va="center")
    ax.text(x_cost + 0.55, head_y, "USD per 1k\ndecisions", color=A.MUTED, fontsize=9, ha="center", va="center")
    ax.plot([0.15, 11.05], [-0.18, -0.18], color=A.STONE, lw=0.8)

    best = {k: max(t[k] for t in tab) for k, _ in cols}
    for i, t in enumerate(tab):
        y = i + 0.3
        ax.text(x_rank, y, str(t["rank"]), fontsize=10.5, va="center",
                color=A.INK if t["rank"] == 1 else A.INK2, fontweight="bold" if t["rank"] == 1 else "normal")
        ax.text(x_model, y, t["model"], fontsize=10.5, va="center", color=A.INK)
        for j, (k, _) in enumerate(cols):
            val = t[k]
            # a saturated benchmark carries no ranking signal: draw it neutral, not as a strength
            face = "#e9e4da" if k == "boundary" else SCORE_CMAP(val / 100)
            ax.add_patch(Rectangle((x0 + w * j + 0.06, y - 0.4), w - 0.12, 0.8, facecolor=face,
                                   edgecolor=A.INK if (k == "overall") else "none", lw=0.6))
            dark = val > 62 and k != "boundary"
            ax.text(x0 + w * j + w / 2, y, _fmt(val), ha="center", va="center", fontsize=10.5,
                    color=A.SURFACE if dark else A.INK,
                    fontweight="bold" if (val == best[k] and k != "boundary") else "normal")
        ax.text(x_comp + 0.5, y, f"{t['completion'] * N_ROWS:.0f}/{N_ROWS}", ha="center", va="center",
                fontsize=10, color=A.INK2)
        ax.text(x_cost + 0.55, y, f"${t['usd_per_1k']:.2f}", ha="center", va="center", fontsize=10, color=A.INK2)
    y_sep = len(tab) + 0.3 - 0.55
    ax.plot([0.15, 11.05], [y_sep, y_sep], color=A.STONE, lw=0.8, ls=(0, (3, 3)))
    for i, t in enumerate(dnf):
        y = len(tab) + i + 0.35
        ax.text(x_rank, y, "–", fontsize=10, va="center", color=A.MUTED)
        ax.text(x_model, y, t["model"], fontsize=10, va="center", color=A.MUTED)
        ax.text(x0 + w * len(cols) / 2, y, f"did not finish: {t['why']}", ha="center", va="center",
                fontsize=9.5, color=A.MUTED, style="italic")
        ax.text(x_comp + 0.5, y, f"{t['valid']}/{t['of']}", ha="center", va="center", fontsize=10, color=A.MUTED)
    fig.text(0.012, 0.975, f"Round {res['round']} scorecard: four sub-benchmarks, one overall rank",
             fontsize=13, color=A.INK, va="top")
    fig.text(0.012, 0.93, "Scores 0–100, higher is better; bold = best in column. Overall = mean of detection, "
             "escalation and uptake. Boundary hold is 100 for every model, so it cannot rank them.",
             fontsize=9.3, color=A.INK2, va="top")
    fig.text(0.012, 0.012, A.SOURCE + "Exploratory secondary ranking; the preregistered primary is boundary hold. Definitions: scorecard_core.py.",
             fontsize=8, color=A.MUTED)
    fig.subplots_adjust(left=0, right=1, top=0.87, bottom=0.05)
    fig.savefig(out, dpi=220)
    plt.close(fig)


def fig_leaderboard(res, out):
    """Decomposed leaderboard: each bar = overall score built from its three equal-weight parts,
    with the story-bootstrap 95% interval on top and P(rank 1) in a side panel."""
    tab = res["table"][::-1]
    n = len(tab)
    parts = [("detection", "reality detection", A.ORANGE), ("escalation", "escalation", A.AQUA),
             ("uptake", "instruction uptake", A.BLUE)]
    fig, (ax, px) = plt.subplots(1, 2, figsize=(10.2, 0.38 * n + 2.3), sharey=True,
                                 gridspec_kw={"width_ratios": [5.2, 1], "wspace": 0.06})
    for i, t in enumerate(tab):
        left = 0.0
        for k, _, c in parts:
            w = t[k] / 3
            ax.barh(i, w, left=left, color=c, height=0.62, edgecolor=A.SURFACE, linewidth=0.6, zorder=2)
            left += w
        lo, hi = t["ci"]["overall"]
        ax.plot([lo, hi], [i, i], color=A.INK, lw=1.0, zorder=4)
        for e in (lo, hi):
            ax.plot([e, e], [i - 0.13, i + 0.13], color=A.INK, lw=1.0, zorder=4)
        ax.text(max(hi, t["overall"]) + 1.6, i, f"{t['overall']:.0f}", va="center", fontsize=8.8,
                color=A.INK if t["rank"] <= 2 else A.INK2)
        px.barh(i, t["p_first"], color=A.INK2 if t["p_first"] > 0 else A.STONE, height=0.5, zorder=2)
        if t["p_first"] >= 0.005:
            px.text(t["p_first"] + 0.04, i, f"{t['p_first']:.0%}", va="center", fontsize=8.3, color=A.INK)
    ax.set_yticks(range(n), [t["model"] for t in tab])
    ax.tick_params(axis="y", length=0, labelsize=9.6, labelcolor=A.INK)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlabel("Overall score (0–100) = sum of the three parts")
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    px.set_xlim(0, 1.25)
    px.set_xticks([0, 1], ["0", "100%"])
    px.set_xlabel("P(rank 1)")
    px.grid(axis="y", visible=False)
    px.spines["left"].set_visible(False)
    px.tick_params(axis="y", length=0)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [Patch(color=c, label=lab) for _, lab, c in parts] + [
        Line2D([], [], color=A.INK, lw=1, marker="|", ms=8, label="95% interval")]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.01, 1 - 0.42 / fig.get_size_inches()[1]), ncol=4, fontsize=8.6,
               handlelength=1.4, columnspacing=1.5)
    fig.suptitle(f"Round {res['round']} leaderboard, decomposed", x=0.01, ha="left", fontsize=12.5, y=0.99)
    fig.text(0.01, 0.03, f"Each part is one sub-benchmark (0–100) divided by 3. Intervals and P(rank 1): paired "
             f"bootstrap over the 6 stories, {res['draws']} resamples.", fontsize=8.2, color=A.INK2)
    fig.text(0.01, 0.006, A.SOURCE.strip(), fontsize=7.8, color=A.MUTED)
    h = fig.get_size_inches()[1]
    fig.subplots_adjust(left=0.19, right=0.985, top=1 - 1.15 / h, bottom=0.95 / h)
    fig.savefig(out, dpi=220)
    plt.close(fig)


def write_md(res, out):
    lines = ["| # | Model | Overall | Boundary hold | Reality detection | Escalation | Instruction uptake "
             "| 95% CI (overall) | P(#1) | USD / 1k |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for t in res["table"]:
        lo, hi = t["ci"]["overall"]
        lines.append(f"| {t['rank']} | {t['model']} | **{t['overall']:.0f}** | {t['boundary']:.0f} | "
                     f"{t['detection']:.0f} | {t['escalation']:.0f} | {t['uptake']:.0f} | {lo:.0f}–{hi:.0f} | "
                     f"{100 * t['p_first']:.0f}% | ${t['usd_per_1k']:.2f} |")
    for t in res["dnf"]:
        lines.append(f"| – | {t['model']} | DNF | | | | | | | {t['valid']}/{t['of']} valid ({t['why']}) |")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="results/round1/all_runs_raw.csv")
    ap.add_argument("--out", default="figures/round1")
    ap.add_argument("--round", default="1", help='label used in titles, e.g. "1" or "1 (rerun)"')
    ap.add_argument("--source", default=A.SOURCE.strip(), help="source line under each figure")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    A.SOURCE = a.source.rstrip() + " "
    A.style()
    res = build(A.load(a.inp), a.round)
    (out / "scorecard.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    write_md(res, out / "scorecard.md")
    fig_scorecard(res, out / "fig12_scorecard.png")
    fig_leaderboard(res, out / "fig13_leaderboard.png")
    print((out / "scorecard.md").read_text(encoding="utf-8"))
    print("without-one:", json.dumps(res["rank_without_one"], indent=1))
    print("pairs:", res["leader_by_pair"])


if __name__ == "__main__":
    main()
