"""Generational chart: does a model family get better at this across versions?

    python generations.py [--in figures/rerun/scorecard.json] [--out figures/rerun/fig15_generations.png]

One panel per family; x = version number, y = overall scorecard score with its
story-bootstrap 95% interval. Only models present in the scorecard are drawn, and a
family needs 2+ models to get a panel. Points in a family's main line are joined;
side variants (other tiers of the same version) are drawn unjoined and labelled.
"""
import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analyze_round1 as A

# family -> [(scorecard label, version, joined into the family line?)]
FAMILIES = {
    "Claude Sonnet": [("Claude Sonnet 4", 4.0, True), ("Claude Sonnet 4.5", 4.5, True),
                      ("Claude Sonnet 4.6", 4.6, True), ("Claude Sonnet 5", 5.0, True)],
    "Claude Opus": [("Claude Opus 4.1", 4.1, True), ("Claude Opus 4.5", 4.5, True),
                    ("Claude Opus 4.6", 4.6, True), ("Claude Opus 4.7", 4.7, True),
                    ("Claude Opus 4.8", 4.8, True), ("Claude Opus 5", 5.0, True)],
    "OpenAI GPT": [("GPT-5.4", 5.4, True), ("GPT-5.5", 5.5, True), ("GPT-6 Astra", 6.0, True),
                   ("GPT-5.4 mini", 5.4, False), ("GPT-5.4 nano", 5.4, False),
                   ("GPT-5.6 Terra", 5.6, False), ("GPT-5.6 Luna", 5.6, False)],
    "Gemini Flash": [("Gemini 2.5 Flash", 2.5, True), ("Gemini 3 Flash", 3.0, True),
                     ("Gemini 3.5 Flash", 3.5, True), ("Gemini 3.6 Flash", 3.6, True),
                     ("Gemini 3.7 Flash", 3.7, True), ("Gemini 3.8 Flash", 3.8, True),
                     ("Gemini 3.1 Flash-Lite", 3.1, False), ("Gemini 3.5 Flash-Lite", 3.5, False)],
    "Gemini Pro": [("Gemini 2.5 Pro", 2.5, True), ("Gemini 3.1 Pro", 3.1, True)],
    "Gemma 4": [("Gemma 4 26B A4B", 4.0, False), ("Gemma 4 31B", 4.0, False)],
}
COLOR = {"Claude Sonnet": A.ORANGE, "Claude Opus": A.RED, "OpenAI GPT": A.AQUA,
         "Gemini Flash": A.BLUE, "Gemini Pro": A.VIOLET, "Gemma 4": A.MAGENTA}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="figures/rerun/scorecard.json")
    ap.add_argument("--out", default="figures/rerun/fig15_generations.png")
    a = ap.parse_args()
    res = json.load(open(a.inp, encoding="utf-8"))
    score = {t["model"]: t for t in res["table"]}
    panels = [(f, [(m, v, j) for m, v, j in ms if m in score]) for f, ms in FAMILIES.items()]
    # a generational panel needs 2+ distinct versions
    panels = [(f, ms) for f, ms in panels if len({v for _, v, _ in ms}) >= 2]
    for f, ms in panels:
        print(f, [(m, round(score[m]["overall"])) for m, _, _ in ms])
    if not panels:
        raise SystemExit("no family has 2+ scored versions yet")

    A.style()
    cols = min(3, len(panels))
    rows = (len(panels) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4.6 * cols, 3.6 * rows + 1.0), squeeze=False, sharey=True)
    for ax in axes.flat[len(panels):]:
        ax.set_visible(False)
    for ax, (fam, ms) in zip(axes.flat, panels):
        c = COLOR[fam]
        versions = sorted({v for _, v, _ in ms})
        pos = {v: i for i, v in enumerate(versions)}
        line = sorted([(pos[v], score[m]["overall"]) for m, v, j in ms if j])
        if len(line) >= 2:
            ax.plot([p[0] for p in line], [p[1] for p in line], color=c, lw=2, alpha=0.7, zorder=2)
        for m, v, joined in ms:
            t = score[m]
            x = pos[v] + (0 if joined else 0.18)
            lo, hi = t["ci"]["overall"]
            ax.plot([x, x], [lo, hi], color=c, lw=1.6, alpha=0.35, zorder=1)
            ax.scatter([x], [t["overall"]], s=62, zorder=3, color=c if joined else A.SURFACE,
                       edgecolor=c, linewidth=1.6)
            if joined:
                ax.annotate(f"{t['overall']:.0f}", (x, hi), xytext=(0, 4), textcoords="offset points",
                            ha="center", fontsize=9.5, color=A.INK, fontweight="semibold")
            else:
                tier = m.split(" ")[-1] if m.split(" ")[-1] in ("mini", "nano", "Luna", "Terra", "Flash-Lite") else m
                ax.annotate(f"{tier} {t['overall']:.0f}", (x, t["overall"]), xytext=(6, -3),
                            textcoords="offset points", fontsize=8.4, color=A.INK2)
        main = {v: m for m, v, j in ms if j}
        ax.set_xticks(range(len(versions)),
                      [(main.get(v) or f"{v:g}").replace("Claude ", "").replace("Gemini ", "") for v in versions],
                      fontsize=8.8)
        ax.set_xlim(-0.4, len(versions) - 0.35)
        ax.set_ylim(-5, 108)
        ax.set_title(fam, fontsize=11.5, pad=6)
        ax.grid(axis="x", visible=False)
    for r in range(rows):
        axes[r][0].set_ylabel("Overall score (0–100)")
    fig.suptitle("Does a newer model handle a real-looking credential better?", x=0.01, ha="left",
                 fontsize=13, color=A.INK)
    fig.text(0.01, 0.94 if rows > 1 else 0.885,
             "Scorecard overall per model family, in release order. Filled = main line; hollow = smaller or "
             "other tiers of that version. Whiskers: story-bootstrap 95% interval.", fontsize=9.3, color=A.INK2)
    fig.text(0.01, 0.005, "Source: Is This Still the Test? scorecard task, Kaggle Benchmarks, 2026-09-27. "
             "Exploratory secondary ranking.", fontsize=8, color=A.MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.925 if rows > 1 else 0.87))
    fig.savefig(a.out, dpi=220)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
