# Copyright (c) 2024-2026 Ketema Harris. All rights reserved.
# SPDX-License-Identifier: LicenseRef-CCABDD-Proprietary
"""Canonical loader for CL12 contract files (headroom/contracts/*.contract.py).

Contract files use a `<name>.contract.py` double-extension naming convention
so they read as executable specifications distinct from regular modules — but
that same naming makes them unreachable via a normal `import` statement
(Python parses the embedded dot as a package separator). Every call site must
therefore load them dynamically via importlib, and MUST register the module
in sys.modules BEFORE exec_module runs: contract files use
`from __future__ import annotations` + `@dataclass`, and dataclasses resolves
`cls.__module__` via `sys.modules.get(...)` while the class body executes. If
the module isn't registered yet, that lookup returns None and dataclass
processing raises `AttributeError: 'NoneType' object has no attribute
'__dict__'`.

This ordering bug previously shipped in headroom/proxy/handlers/streaming.py,
which reimplemented the load inline (spec_from_file_location +
module_from_spec + exec_module, no sys.modules registration) against a
hardcoded absolute path outside the installed package — broken for every
install except the one machine that path happened to exist on. Do not
reimplement this dance at a new call site; use the functions below instead.

load_contract_from_path() is pure stdlib (importlib.util + sys) and has no
dependency on the `headroom` package itself — see
tests/test_contract_loading.py, which loads this file directly by path
(bypassing `import headroom`, same technique headroom/release_version.py
already uses) so the regression suite for this exact bug does not require
the compiled `headroom._core` Rust extension to run.

load_contract() is the headroom-aware convenience wrapper: it resolves a
contract's location via importlib.resources (works under an editable
install, a built wheel, or a zipapp — never a hardcoded filesystem path)
and delegates to load_contract_from_path().
"""
from __future__ import annotations

import importlib.resources
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_contract_from_path(module_name: str, contract_path: Path | str) -> ModuleType:
    """Load the `.py` file at contract_path, registered in sys.modules as module_name.

    Idempotent: a second call with the same module_name returns the cached
    module from sys.modules rather than re-executing the file — re-execution
    would create a second, distinct set of dataclass/exception types that
    fail isinstance/equality checks against the first load's types.
    """
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached

    contract_path = Path(contract_path)
    if not contract_path.is_file():
        raise FileNotFoundError(f"contract file not found: {contract_path}")

    spec = importlib.util.spec_from_file_location(module_name, contract_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build a loader for contract at {contract_path}")
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: dataclass processing inside the contract body
    # resolves cls.__module__ via sys.modules while the class is defined.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Do not leave a half-initialized module cached under this name.
        sys.modules.pop(module_name, None)
        raise
    return module


def load_contract(module_name: str, filename: str) -> ModuleType:
    """Load `headroom/contracts/<filename>` as a module registered as `module_name`.

    Resolves the file via importlib.resources so it works under any install
    shape (editable, built wheel, zipapp) — never a hardcoded filesystem path.
    """
    resource = importlib.resources.files("headroom.contracts").joinpath(filename)
    with importlib.resources.as_file(resource) as contract_path:
        return load_contract_from_path(module_name, contract_path)
