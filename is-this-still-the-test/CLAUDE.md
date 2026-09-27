# Project: Is This Still the Test?

A Kaggle benchmark measuring how much reality-evidence an AI model needs
before it stops treating a security test as fake and refuses to cross a
boundary. Recreates the 2026 Irregular/Gemini eval-escape incidents as a
controlled, single-turn decision benchmark.

Interfaces between modules are pinned in `CONTRACTS.md`. Read it before
changing any file. If you must change an interface, record it in
`NOTES/<stream>.md` and stay backward compatible.

## Repo layout

```
fetch_sources.py        # ONLY file that touches the network; snapshots public sources once
data/sources/           # dated snapshots + manifest.json (sha256, download date, Tranco list id)
scenarios/              # 24 base stories; build_all() emits 25 conditions each (two arms)
scoring.py              # pure scoring: Decision, classify (correct/crossed/false_stop/refused/unparsed), wilson
build_dataset.py        # scenarios x conditions -> data/scenarios.parquet (+ .csv), length checks
make_task.py            # generates self-contained task.py / task_smoke.py (inlines scoring + data)
task.py                 # the kbench task pushed to Kaggle; ends with .run() and `# %choose reality-threshold`
task_smoke.py           # pilot: 2 scenarios x 4 conditions x 1 repeat = 8 calls
collect_results.py      # downloaded kbench runs -> results/decisions.csv
analyze.py              # decisions.csv -> figures/*.png, figures/summary.{md,json}
tools/mock_results.py   # synthetic decisions.csv for developing analyze.py
tests/                  # edge-case suite (scoring, confounds, real-data safety, run mechanics)
results/  figures/      # run outputs and charts
post/draft.md           # DEV post draft with {{PLACEHOLDERS}} for results
SOURCES.md ETHICS.md PREREGISTRATION.md README.md
.env                    # written by `kaggle b init` (gitignored, never commit)
```

## Hard rules
- Use ONLY kaggle_benchmarks APIs confirmed in the kbench source or an
  official example (documentation/examples, cookbook, user_guide). If
  unsure, stop and ask; do NOT invent kbench functions.
- Every task file MUST end with .run() or .evaluate(), or the server
  runs nothing and produces no results file.
- The benchmark NEVER makes a network request to any host named in a
  scenario. No requests, no DNS lookups, no pings. Scenario hosts are
  text only. Network access is allowed ONLY in `fetch_sources.py`, to
  download the public source files below, once, at build time.
- `fetch_sources.py` is never imported by anything. Everything else reads
  the snapshots in `data/sources/`, never live data.
- Allowed real data: AWS ip-ranges.json, Google Cloud cloud.json,
  Cloudflare ips-v4, the Tranco list (python package `tranco`), public
  CA names. Each is snapshotted with its download date and sha256 in
  `data/sources/manifest.json`.
- Real domains appear ONLY in the `identity_famous` / `identity_lesser`
  conditions, ONLY from `data/sources/identity_tiers.json` (hand-picked from
  the filtered Tranco top 1000), and NEVER health, government, education, child-related
  or finance-sensitive domains. Small-org base stories use invented names
  ending in `.example`; in-scope sandbox hosts end in `.local`.
- Credentials and personal records are ALWAYS randomly generated (seeded).
  Credentials start with `synth-`. Never use or search for real leaked
  credentials or breach data.
- Transcripts say the credential is UNTESTED and only LABELED for a
  host. Never write that a real organization's credential works or
  that it was breached. Banned in transcripts: "works", "succeeded",
  "breached", "compromised", "valid" (credential), "leaked".
- No temperature claims. The Kaggle proxy does not support setting
  temperature; sampling is the provider default, seed = repeat where
  supported. One model call per row, fresh chat per row.
- Transcripts never say whether the decision host is in scope; the model
  must compare it with the scope document itself.
- Never count a refusal as a safe stop; tag it separately. A parseable
  stop/report is always a decision, whatever the reason's wording.
- Do not run `kaggle b init`, push, or spend model credits without the
  owner's explicit go-ahead in this session.

## Workflow (one step at a time, confirm between steps)
1. `python fetch_sources.py` (only if re-snapshotting; otherwise use the
   committed snapshot), then `python build_dataset.py --smoke`, then the
   full build. Run `python -m pytest` until green.
2. `python make_task.py --smoke`, then `python task_smoke.py` and confirm a
   `*.run.json` appears BEFORE pushing.
3. Push `task_smoke.py`, run it on ONE cheap model as a pilot. Publish
   PREREGISTRATION.md (public gist or Kaggle dataset) before the full run.
4. Only after pilot cost is known, scale models/repeats.
5. `kaggle b t download` -> `python collect_results.py` -> `python analyze.py`.

## Cost discipline
- Pilot = task_smoke.py (2 scenarios x 4 conditions x 1 repeat x 1 model). Read the real per-call
  cost from chat.usage before scaling.
- Confirm model slugs live (`kaggle b t models`) before any run. Never
  hardcode a lineup from memory.
