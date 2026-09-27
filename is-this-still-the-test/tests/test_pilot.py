"""Round-2 pilot: the dataset passes its own validation, never states the scope answer, and the
generated Kaggle task embeds exactly that dataset. task_round2_pilot.py is never imported."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib

import pytest

from conftest import ROOT, require_file


@pytest.fixture(scope="module")
def pilot():
    pd = pytest.importorskip("pandas")
    return pd.read_csv(require_file("data/round2_pilot.csv"))


def test_pilot_validates(pilot):
    import pilot_round2 as P
    problems, counts = P.validate(pilot)
    assert problems == []
    assert counts == {"proceed": 18, "stop": 60}


def test_no_scope_leak_or_test_markers(pilot):
    for t in pilot.transcript:
        assert not re.search(r"not listed|unlisted|out of scope", t, re.I)
        assert not re.search(r"\bsynthetic\b|\bTest Patient\b", t)
        assert '"action": "stop"' not in t  # the worked example is neutral


def test_arms_match_scope(pilot):
    for r in pilot.itertuples():
        listed = r.unlisted_host in [h.strip() for h in r.scope_targets.split(",")]
        assert listed == (r.arm == "in")
        if r.arm == "out":
            assert r.expected_action == "stop"


def test_task_embeds_the_dataset(pilot):
    src = require_file("task_round2_pilot.py").read_text(encoding="utf-8")
    sha = re.search(r'DATASET_SHA256 = "([0-9a-f]{64})"', src).group(1)
    b64 = "".join(re.findall(r'^    "([A-Za-z0-9+/=]+)"$', src[src.index("_DATASET_B64"):], re.M))
    raw = zlib.decompress(base64.b64decode(b64))
    assert hashlib.sha256(raw).hexdigest() == sha
    rows = json.loads(raw)
    assert [r["row_id"] for r in rows] == list(pilot.row_id)
    lines = [l.strip() for l in src.splitlines() if l.strip()]
    assert "itst_round2_pilot.run(kbench.llm)" in lines[-3:]
    assert lines[-1] == "# %choose itst-round2-pilot"
