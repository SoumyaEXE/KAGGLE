"""One command after each day's Kaggle runs: collect every download, rebuild every chart,
re-render the post and the paper.

    kaggle b t download reality-threshold-scorecard -o results/raw      (one download at a time)
    kaggle b t download itst-round2-pilot -o results/raw
    python tools/refresh_all.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = {"reality-threshold": "results/round1", "reality-threshold-scorecard": "results/rerun",
         "itst-round2-pilot": "results/pilot"}


def run(*cmd):
    print("$", " ".join(cmd))
    subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)


def main():
    for task, out in TASKS.items():
        if (ROOT / "results/raw" / task).exists():
            (ROOT / out).mkdir(parents=True, exist_ok=True)
            run("tools/build_all_runs.py", "--raw", f"results/raw/{task}", "--out", f"{out}/all_runs_raw.csv")
    run("analyze_round1.py")
    run("figures_story.py")
    run("scorecard.py")
    run("scorecard.py", "--in", "results/rerun/all_runs_raw.csv", "--out", "figures/rerun", "--round", "1 (Kaggle rerun)",
        "--source", "Source: Is This Still the Test? scorecard task, fresh Kaggle runs.")
    run("compare_runs.py")
    run("generations.py")
    run("figures_final.py")
    if (ROOT / "results/pilot/all_runs_raw.csv").exists():
        run("analyze_pilot.py")
    run("tools/render_post.py")
    run("paper/build_paper.py")
    print("\nall refreshed: figures/final, post/dev_post_final.md, paper/main.pdf")


if __name__ == "__main__":
    main()
