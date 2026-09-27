"""One place where a broken module is reported. Every other test that needs the module
skips with a pointer here, so a syntax error in e.g. scenarios/common.py shows up as ONE
clear failure instead of dozens of fixture errors."""
from __future__ import annotations

import pytest

from conftest import ROOT, require_file, try_import

MODULES = [
    ("scoring", "scoring.py"),
    ("scenarios.common", "scenarios/common.py"),
    ("scenarios", "scenarios/__init__.py"),
    ("collect_results", "collect_results.py"),
    ("build_dataset", "build_dataset.py"),
]


@pytest.mark.parametrize("module,rel", MODULES, ids=[m for m, _ in MODULES])
def test_module_imports(module, rel):
    require_file(rel)
    if module == "scenarios" and (ROOT / "scenarios" / "common.py").exists():
        try:
            try_import("scenarios.common")
        except BaseException:
            pytest.skip("scenarios/common.py fails to import; reported once by "
                        "test_module_imports[scenarios.common]")
    try_import(module)
