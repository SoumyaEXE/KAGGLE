"""Convert downloaded kbench run outputs into results/decisions.csv (CONTRACTS v2, C -> E).

    kaggle b t download reality-threshold -o results/raw
    python collect_results.py                       # results/raw -> results/decisions.csv
    python collect_results.py --in DIR --out FILE --dataset data/scenarios.parquet

Input format (verified against kaggle-benchmarks 0.6.1 source and a local run):
  `kaggle b t download` extracts each run's output zip to
  <out>/<task>/<version>/<model>/<run_id>/. Inside:
  * reality-threshold-run_id_Run_1_<model>.run.json  (protobuf BenchmarkTaskRun as JSON,
    camelCase keys). Top level: taskVersion, modelVersion.slug, state, results
    ([{"numericResult": {"value", "confidenceInterval"}}]) and `subruns`: one entry per
    row attempt, each with state BENCHMARK_TASK_RUN_STATE_COMPLETED|ERRORED and, when
    completed, results[0].dictResult = the dict returned by the itst-decision task
    (protobuf Struct: every number comes back as a float).
  * itst-decision-*.run.json (only if not pruned; same dictResult shape at top level)
  * itst_decisions.jsonl (one JSON object per row; status completed|errored)
All three are read; rows are de-duplicated on (model, row_id, repeat), completed
beats errored, and among completed copies the latest parent run wins.

Outcomes are RE-SCORED locally from raw_text with scoring.py (so a scoring fix never
needs a new model run); the count of rows whose outcome changed vs the on-server
classification is printed.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scoring  # noqa: E402

ROW_TASK = "itst-decision"
OUT_COLUMNS = ["model", "scenario_id", "condition", "arm", "experiment", "level", "cue_type",
               "framing", "mitigation", "is_real_domain", "identity_tier", "expected_action", "repeat",
               "action", "is_target_in_scope", "believes_real_external_system", "confidence", "reason",
               "outcome", "crossed", "false_stop", "correct", "know_do_gap", "real_but_proceeded",
               "token_len"]


def canonical_model(slug) -> str:
    """Same normalization the kaggle CLI applies: drop provider prefix, '@' -> '-'."""
    s = str(slug or "unknown").strip()
    return s.split("/")[-1].replace("@", "-")


def dataset_sha(df: pd.DataFrame) -> str:
    """Identical to make_task's embedded-dataset hash, so results can be matched to a dataset."""
    from make_task import dataset_sha as _sha
    return _sha(df)


def _dict_result(run: dict):
    for r in run.get("results") or []:
        if isinstance(r, dict) and isinstance(r.get("dictResult"), dict):
            return r["dictResult"]
    return None


def iter_records(in_dir: Path):
    """Yield (record_dict, status, sort_key, source) from every supported file."""
    for p in sorted(in_dir.rglob("*.run.json")):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"skip unreadable {p}: {e}", file=sys.stderr)
            continue
        slug = (run.get("modelVersion") or {}).get("slug")
        end = str(run.get("endTime") or "")
        candidates = [run] + list(run.get("subruns") or [])
        for sub in candidates:
            name = ((sub.get("taskVersion") or {}).get("name") or "")
            d = _dict_result(sub)
            if d is None or name != ROW_TASK:
                continue
            state = str(sub.get("state", ""))
            status = "completed" if state.endswith("COMPLETED") else "errored"
            rec = dict(d)
            rec.setdefault("model", slug)
            yield rec, status, (end, str(sub.get("endTime") or "")), str(p)
    for p in sorted(in_dir.rglob("itst_decisions*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            yield rec, rec.get("status", "completed"), ("", ""), str(p)


def collect(in_dir: Path, dataset: pd.DataFrame, valid_shas: set) -> tuple[pd.DataFrame, dict]:
    best = {}
    errored = set()
    stats = {"records": 0, "sha_mismatch": 0, "unknown_row_id": 0}
    known = set(dataset.row_id)
    for rec, status, key, src in iter_records(in_dir):
        stats["records"] += 1
        rid = str(rec.get("row_id"))
        if rid not in known:
            stats["unknown_row_id"] += 1
            continue
        if rec.get("dataset_sha256") and rec["dataset_sha256"] not in valid_shas:
            stats["sha_mismatch"] += 1
        k = (canonical_model(rec.get("model")), rid, int(float(rec.get("repeat", 0) or 0)))
        if status != "completed" or "outcome" not in rec:
            errored.add(k)
            continue
        if k not in best or key >= best[k][0]:
            best[k] = (key, rec)
    stats["errored_only"] = len(errored - set(best))

    meta = dataset.set_index("row_id")
    rows, changed = [], 0
    for (model, rid, rep), (_, rec) in sorted(best.items()):
        m = meta.loc[rid]
        raw = rec.get("raw_text")
        if isinstance(raw, str):
            c = scoring.classify(None, raw, m.decision_host, m.scope_targets, m.expected_action)
        else:  # no raw text persisted: trust the on-server classification
            c = {"outcome": rec.get("outcome"), "crossed": bool(rec.get("crossed")),
                 "false_stop": bool(rec.get("false_stop")), "correct": bool(rec.get("correct")),
                 "know_do_gap": bool(rec.get("know_do_gap")),
                 "real_but_proceeded": bool(rec.get("real_but_proceeded")),
                 "action": rec.get("action"), "in_scope_claim": rec.get("is_target_in_scope"),
                 "believes_real": rec.get("believes_real_external_system")}
        if c["outcome"] != rec.get("outcome"):
            changed += 1
        d = scoring.parse_decision(raw) if isinstance(raw, str) else None
        conf = d.confidence if d is not None else rec.get("confidence")
        reason = d.reason if d is not None else rec.get("reason")
        rows.append({
            "model": model, "scenario_id": m.scenario_id, "condition": m.condition, "arm": m.arm,
            "experiment": m.experiment, "level": int(m.level), "cue_type": m.cue_type,
            "framing": m.framing, "mitigation": bool(m.mitigation),
            "is_real_domain": bool(m.is_real_domain), "identity_tier": m.identity_tier,
            "expected_action": m.expected_action, "repeat": rep,
            "action": c["action"], "is_target_in_scope": c["in_scope_claim"],
            "believes_real_external_system": c["believes_real"],
            "confidence": None if conf is None else int(round(float(conf))),
            "reason": reason, "outcome": c["outcome"], "crossed": bool(c["crossed"]),
            "false_stop": bool(c["false_stop"]), "correct": bool(c["correct"]),
            "know_do_gap": bool(c["know_do_gap"]), "real_but_proceeded": bool(c["real_but_proceeded"]),
            "token_len": int(m.token_len),
        })
    stats["rescored_changed"] = changed
    out = pd.DataFrame(rows, columns=OUT_COLUMNS)
    out["confidence"] = out["confidence"].astype("Int64")
    return out, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_dir", default=str(ROOT / "results" / "raw"))
    ap.add_argument("--out", default=str(ROOT / "results" / "decisions.csv"))
    ap.add_argument("--dataset", default=str(ROOT / "data" / "scenarios.parquet"))
    args = ap.parse_args(argv)

    in_dir = Path(args.in_dir)
    if not in_dir.is_dir():
        print(f"input directory not found: {in_dir}\n"
              f"download first: kaggle b t download reality-threshold -o {in_dir}", file=sys.stderr)
        return 2
    dataset = pd.read_parquet(args.dataset)
    shas = {dataset_sha(dataset)}
    smoke = Path(args.dataset).with_name("scenarios_smoke.parquet")
    if smoke.exists():
        shas.add(dataset_sha(pd.read_parquet(smoke)))

    df, stats = collect(in_dir, dataset, shas)
    if df.empty:
        print(f"no completed {ROW_TASK} decisions found under {in_dir} ({stats})", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"wrote {out}: {len(df)} decisions, models={sorted(df.model.unique())}")
    print(f"  records read={stats['records']}  errored (never completed)={stats['errored_only']}  "
          f"unknown row_id={stats['unknown_row_id']}  outcome changed by local rescoring={stats['rescored_changed']}")
    if stats["sha_mismatch"]:
        print(f"  WARNING: {stats['sha_mismatch']} records came from a dataset whose sha256 matches neither "
              f"{args.dataset} nor the smoke parquet; transcripts may differ from the local data.")
    print(df.groupby(["model", "outcome"]).size().unstack(fill_value=0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
