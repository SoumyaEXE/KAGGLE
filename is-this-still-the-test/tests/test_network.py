"""Edge case 16: nothing in the build path may resolve or contact any host.

socket.socket.connect, socket.getaddrinfo, socket.gethostbyname,
socket.create_connection, http.client, urllib.request.urlopen and requests are
patched to RECORD and RAISE. Then scenarios.build_all() runs in-process and
build_dataset.py --smoke runs in a subprocess (inside a temp copy of the repo so
the real data/scenarios.parquet is never overwritten).
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import ROOT, SOURCES, import_or_skip, require_file


@pytest.fixture
def scenarios_importable():
    """Skip (pointing to tests/test_imports.py) if scenarios/ does not even import;
    works for both v1 and v2 scenarios, the network rule applies to both."""
    import_or_skip("scenarios", "scenarios/__init__.py")

GUARD = r'''
import socket, urllib.request, http.client
CALLS = []
class NetworkBlocked(RuntimeError):
    pass
def _block(name):
    def f(*a, **k):
        CALLS.append((name, repr(a)[:200]))
        raise NetworkBlocked(f"network call blocked: {name}{a!r}")
    return f
socket.socket.connect = _block("socket.connect")
socket.socket.connect_ex = _block("socket.connect_ex")
socket.getaddrinfo = _block("socket.getaddrinfo")
socket.gethostbyname = _block("socket.gethostbyname")
socket.gethostbyname_ex = _block("socket.gethostbyname_ex")
socket.create_connection = _block("socket.create_connection")
http.client.HTTPConnection.connect = _block("http.client.connect")
urllib.request.urlopen = _block("urllib.request.urlopen")
try:
    import requests
    requests.Session.request = _block("requests.Session.request")
    requests.api.request = _block("requests.api.request")
except ImportError:
    pass
'''


def _install_guard(monkeypatch):
    ns: dict = {}
    import http.client
    import socket
    import urllib.request

    calls: list = []

    def block(name):
        def f(*a, **k):
            calls.append((name, repr(a)[:200]))
            raise RuntimeError(f"network call blocked: {name}")
        return f

    monkeypatch.setattr(socket.socket, "connect", block("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", block("socket.connect_ex"))
    monkeypatch.setattr(socket, "getaddrinfo", block("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", block("socket.gethostbyname"))
    monkeypatch.setattr(socket, "gethostbyname_ex", block("socket.gethostbyname_ex"))
    monkeypatch.setattr(socket, "create_connection", block("socket.create_connection"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", block("http.client.connect"))
    monkeypatch.setattr(urllib.request, "urlopen", block("urllib.request.urlopen"))
    try:
        import requests
        monkeypatch.setattr(requests.Session, "request", block("requests.Session.request"))
    except ImportError:
        pass
    return calls


def test_guard_actually_blocks(monkeypatch):
    """Self-test: prove the guard would catch a lookup, so a pass is meaningful."""
    import socket
    calls = _install_guard(monkeypatch)
    with pytest.raises(RuntimeError):
        socket.getaddrinfo("brightsmile-dental-portal.example", 443)
    assert calls


def test_16_build_all_makes_zero_network_calls(monkeypatch):
    scenarios_pkg = import_or_skip("scenarios", "scenarios/__init__.py")  # v1 or v2
    require_file("data/sources")
    calls = _install_guard(monkeypatch)
    rows = scenarios_pkg.build_all(sources_dir=str(SOURCES), seed=7)
    assert rows
    assert calls == [], f"build_all attempted network access: {calls}"


@pytest.mark.slow
def test_16_build_dataset_smoke_makes_zero_network_calls(tmp_path, scenarios_importable):
    require_file("build_dataset.py")
    require_file("data/sources")
    work = tmp_path / "repo"
    work.mkdir()
    for src in ROOT.glob("*.py"):
        shutil.copy2(src, work / src.name)
    shutil.copytree(ROOT / "scenarios", work / "scenarios",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "data" / "sources", work / "data" / "sources")
    runner = work / "_run_guarded.py"
    runner.write_text(GUARD + textwrap.dedent('''
        import json, runpy, sys, os
        sys.path.insert(0, os.getcwd())
        sys.argv = ["build_dataset.py", "--smoke"]
        err = None
        try:
            runpy.run_path("build_dataset.py", run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None):
                err = f"SystemExit({e.code})"
        except BaseException as e:
            err = f"{type(e).__name__}: {e}"
        print("@@RESULT@@" + json.dumps({"calls": CALLS, "error": err}))
    '''), encoding="utf-8")
    p = subprocess.run([sys.executable, str(runner)], cwd=work, capture_output=True,
                       text=True, timeout=300)
    line = [ln for ln in p.stdout.splitlines() if ln.startswith("@@RESULT@@")]
    assert line, f"runner produced no result.\nstdout:\n{p.stdout[-2000:]}\nstderr:\n{p.stderr[-2000:]}"
    res = json.loads(line[-1][len("@@RESULT@@"):])
    assert res["calls"] == [], f"build_dataset --smoke attempted network access: {res['calls']}"
    assert res["error"] is None, f"build_dataset --smoke failed: {res['error']}\n{p.stderr[-2000:]}"


# ------------------------------------------------ static import checks

NETWORK_MODULES = {"fetch_sources", "requests", "httpx", "urllib3", "aiohttp", "tranco"}


def _imports(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    # task.py may contain notebook magics such as "%choose x"; drop them to parse.
    src = "\n".join("" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Call) and getattr(n.func, "id", None) == "__import__":
            if n.args and isinstance(n.args[0], ast.Constant):
                mods.add(str(n.args[0].value))
        elif isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "import_module":
            if n.args and isinstance(n.args[0], ast.Constant):
                mods.add(str(n.args[0].value))
    return mods


@pytest.mark.parametrize("rel", ["task.py", "task_smoke.py", "build_dataset.py", "scoring.py", "make_task.py", "collect_results.py"])
def test_16_no_fetch_sources_or_network_imports(rel):
    p = require_file(rel)
    mods = _imports(p)
    top = {m.split(".")[0] for m in mods}
    bad = top & NETWORK_MODULES
    if "urllib" in top and any(m.startswith("urllib.request") or m == "urllib" for m in mods):
        bad.add("urllib.request")
    if "socket" in top:
        bad.add("socket")
    assert not bad, f"{rel} imports network-capable modules: {sorted(bad)}"


def test_16_scenarios_package_has_no_network_imports(scenarios_importable):
    bad = {}
    for p in (ROOT / "scenarios").rglob("*.py"):
        top = {m.split(".")[0] for m in _imports(p)}
        hit = top & (NETWORK_MODULES | {"socket"})
        if hit:
            bad[str(p.relative_to(ROOT))] = sorted(hit)
    assert not bad, bad
