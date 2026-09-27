#!/usr/bin/env bash
# Round-1 rerun for the models that failed on 2026-09-26 (quota / 429 / 404).
# Scheduled for 2026-09-27 after the Kaggle model quota resets. Log: results/round1/rerun_2026-09-27.log
set -u
cd "$(dirname "$0")/.." || exit 1
export PYTHONUTF8=1
LOG=results/round1/rerun_2026-09-27.log
{
  echo "== rerun started $(date -Is)"
  kaggle b t run reality-threshold \
    -m claude-opus-5-default -m gpt-5.5-2026-04-23 -m deepseek-r1-0528 \
    -m gpt-oss-120b -m grok-4.6 --wait
  kaggle b t download reality-threshold -o results/raw
  if kaggle b t log reality-threshold -m grok-4.6 2>&1 | grep -q 'model "xai/grok-4.6" was not found'; then
    echo "DROPPED grok-4.6 $(date -Is): Kaggle lists the slug in 'kaggle b t models' but every call returns" \
         "404 'The requested model \"xai/grok-4.6\" was not found' (runs 3233497, 3238219 and this rerun)." \
      | tee -a results/round1/DROPPED_MODELS.md
  fi
  echo "== rerun finished $(date -Is)"
} >> "$LOG" 2>&1
