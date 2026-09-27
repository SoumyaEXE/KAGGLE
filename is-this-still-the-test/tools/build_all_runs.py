"""Round-1 run log: every downloaded kbench run -> results/round1/all_runs_raw.csv.

Reads results/raw/reality-threshold/<version>/<model>/<run_id>/itst_decisions.jsonl and, for
rows that errored, the exception message from the matching itst-decision-*.result.json.
One output row per (run, row_id, repeat). `valid` = a parsed stop/report/proceed decision.

    python tools/build_all_runs.py [--raw results/raw/reality-threshold] [--out results/round1/all_runs_raw.csv]
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def run_rows(run_dir: Path, version: str, model_dir: str):
    jl = run_dir / "itst_decisions.jsonl"
    if not jl.exists():
        return []
    errors = {}
    for f in run_dir.glob("itst-decision-*.result.json"):
        info = json.loads(f.read_text(encoding="utf-8")).get("exception_info") or {}
        if info:
            errors[f.name] = f"{info.get('exception_type', '')}: {info.get('exception_message', '')}"
    rows = []
    for line in jl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = f"{r['row_id'].replace('::', '')}-r{r.get('repeat', 0)}_"
        r["error"] = next((e for n, e in errors.items() if key in n), "")
        r.update(task_version=int(version), model_dir=model_dir, run_id=int(run_dir.name))
        r["valid"] = r.get("status") == "completed" and r.get("outcome") in ("safe", "crossed")
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="results/raw/reality-threshold")
    ap.add_argument("--out", default="results/round1/all_runs_raw.csv")
    a = ap.parse_args()
    rows = []
    for vdir in sorted(Path(a.raw).iterdir()):
        for mdir in sorted(p for p in vdir.iterdir() if p.is_dir()):
            for rdir in sorted(p for p in mdir.iterdir() if p.is_dir()):
                rows += run_rows(rdir, vdir.name, mdir.name)
    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False)
    print(df.groupby(["model_dir", "task_version", "run_id"]).valid.agg(["size", "sum"]).to_string())


if __name__ == "__main__":
    main()
