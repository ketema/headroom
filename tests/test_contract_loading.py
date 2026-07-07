# Copyright (c) 2024-2026 Ketema Harris. All rights reserved.
# SPDX-License-Identifier: LicenseRef-CCABDD-Proprietary
"""Regression tests for headroom/_contract_loading.py.

Pins the exact bug that shipped in headroom/proxy/handlers/streaming.py:
`.contract.py` files use `from __future__ import annotations` + `@dataclass`,
and dataclasses resolves `cls.__module__` via `sys.modules` while the class
body executes. A module built via `importlib.util.module_from_spec` +
`exec_module` that is NOT registered in `sys.modules` first makes that
lookup return None, and dataclass processing raises
`AttributeError: 'NoneType' object has no attribute '__dict__'`.

Loaded via direct file path (bypassing `import headroom`, same technique
headroom/release_version.py already uses for its bare-script fallback) so
this test suite does not require the compiled `headroom._core` Rust
extension to run — the bug and its fix are both pure importlib/dataclasses
mechanics, independent of the rest of the package.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOADER_PATH = _REPO_ROOT / "headroom" / "_contract_loading.py"
_CONTRACT_PATH = _REPO_ROOT / "headroom" / "contracts" / "ccr_strip.contract.py"


def _load_bare(module_name: str, path: Path):
    """Load a single .py file by path, bypassing `import headroom` (no _core needed)."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build a loader for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_bare_unregistered(module_name: str, path: Path):
    """Reproduce the ORIGINAL bug: exec_module WITHOUT sys.modules registration
    (this is exactly what headroom/proxy/handlers/streaming.py did before the fix).
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build a loader for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # <-- missing sys.modules[name] = module
    return module


class TestOldPatternStillCrashes:
    """Characterization test: pins WHY register-before-exec is load-bearing.

    Not the RED/GREEN pair for the fix itself (see TestLoadContractFromPath
    below) — documents the underlying dataclasses/sys.modules mechanism so a
    future "simplification" that drops the registration line regresses
    loudly in CI instead of shipping the AttributeError again.
    """

    def test_unregistered_exec_raises_attribute_error(self):
        with pytest.raises(AttributeError, match="NoneType"):
            _load_bare_unregistered("_ccr_strip_repro_unregistered", _CONTRACT_PATH)


class TestLoadContractFromPath:
    """RED (pre-fix): headroom/_contract_loading.py does not exist yet, so
    building a loader for it raises. GREEN (post-fix): load_contract_from_path
    registers the module in sys.modules BEFORE exec_module and returns it
    successfully.
    """

    def setup_method(self):
        for name in list(sys.modules):
            if name.startswith("_ccr_strip_via_loader"):
                del sys.modules[name]

    def test_loader_module_loads_and_registers_before_exec(self):
        loader = _load_bare("_headroom_contract_loading_under_test_1", _LOADER_PATH)
        module = loader.load_contract_from_path("_ccr_strip_via_loader", _CONTRACT_PATH)
        assert sys.modules["_ccr_strip_via_loader"] is module
        assert callable(module.walk_and_strip)

    def test_loader_is_idempotent(self):
        loader = _load_bare("_headroom_contract_loading_under_test_2", _LOADER_PATH)
        first = loader.load_contract_from_path("_ccr_strip_via_loader", _CONTRACT_PATH)
        second = loader.load_contract_from_path("_ccr_strip_via_loader", _CONTRACT_PATH)
        assert first is second

    def test_walk_and_strip_functions_correctly_once_loaded(self):
        loader = _load_bare("_headroom_contract_loading_under_test_3", _LOADER_PATH)
        module = loader.load_contract_from_path("_ccr_strip_via_loader", _CONTRACT_PATH)
        sanitized, count = module.walk_and_strip("before <<ccr:abc123def456>> after")
        assert sanitized == "before  after"
        assert count == 1
