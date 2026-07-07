# Copyright (c) 2024-2026 Ketema Harris. All rights reserved.
# SPDX-License-Identifier: LicenseRef-CCABDD-Proprietary

"""
CCR Strip Contract — PRE/POST/INV/ERRORS/FORBIDDEN for stripping CCR tokens
from outbound tool_use input parameters in the headroom proxy.

AUTHORITY: requirements/REQUIREMENT_MANIFEST_CCR_STRIP.md
CL12-E: every observable behavior in this module traces to a contract clause.

Clause coverage map:

    strip_ccr_from_tool_input()  — PRE-STRIP-1..3, POST-STRIP-1..4,
                                   INV-STRIP-1..3, ERRORS-STRIP-1..2,
                                   FORBIDDEN-STRIP-1..3
    is_write_tool()              — PRE-IS-1, POST-IS-1
    walk_and_strip()             — PRE-WALK-1, POST-WALK-1..2, INV-WALK-1
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set

# ---------------------------------------------------------------------------
# 1. Importable constants (contract authority)
# ---------------------------------------------------------------------------

# CCR token regex — must match headroom's SmartCrusher._extract_ccr_hashes
CCR_TOKEN_PATTERN: str = r"<<ccr:([a-f0-9]{12,24})\b[^>]*>>"
CCR_TOKEN_RE: re.Pattern[str] = re.compile(CCR_TOKEN_PATTERN)

# Default write tools — tools whose input parameters get CCR tokens stripped.
# This is the DEFAULT set; callers can override via exclude_tools parameter.
DEFAULT_WRITE_TOOLS: FrozenSet[str] = frozenset({
    "memory.remember",
    "memory.delete",
    "Write",
    "Edit",
    "mcp__memory__memory_remember",
    "mcp__memory__memory_delete",
})

# Log event name for observability
STRIP_LOG_EVENT: str = "ccr_tokens_stripped"

# ---------------------------------------------------------------------------
# 2. Exception classes
# ---------------------------------------------------------------------------


class CCRStripError(Exception):
    """Base exception for CCR strip contract violations."""

    def __init__(self, message: str, *, clause: str = "", **kwargs: Any) -> None:
        self.clause = clause
        self.payload = kwargs
        super().__init__(f"[{clause}] {message}" if clause else message)


class InvalidToolNameError(CCRStripError):
    """PRE-STRIP-1: tool_name must be a non-empty string."""

    def __init__(self, tool_name: Any, *, clause: str = "PRE-STRIP-1") -> None:
        super().__init__(
            f"tool_name must be a non-empty string, got {type(tool_name).__name__}",
            clause=clause,
            rejected=repr(tool_name),
        )


class InvalidInputJSONError(CCRStripError):
    """PRE-STRIP-2: input_json must be a dict."""

    def __init__(self, input_json: Any, *, clause: str = "PRE-STRIP-2") -> None:
        super().__init__(
            f"input_json must be a dict, got {type(input_json).__name__}",
            clause=clause,
            rejected=repr(input_json),
        )


class InvalidExcludeSetError(CCRStripError):
    """PRE-STRIP-3: exclude_tools must be a set or frozenset."""

    def __init__(self, exclude_tools: Any, *, clause: str = "PRE-STRIP-3") -> None:
        super().__init__(
            f"exclude_tools must be a set/frozenset, got {type(exclude_tools).__name__}",
            clause=clause,
            rejected=repr(exclude_tools),
        )


class StripFailedError(CCRStripError):
    """ERRORS-STRIP-3: exception during CCR strip — fail-open, forward unchanged."""

    def __init__(self, cause: Exception, *, clause: str = "ERRORS-STRIP-3") -> None:
        super().__init__(
            f"CCR strip failed: {cause}",
            clause=clause,
            cause=str(cause),
        )


# ---------------------------------------------------------------------------
# 3. Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StripResult:
    """Result of CCR token stripping.

    INV-STRIP-3: tool_name and original_tool_name are identical.
    """

    tool_name: str
    sanitized_input: Dict[str, Any]
    tokens_found: int
    tokens_stripped: int
    was_stripped: bool


@dataclass(frozen=True)
class StripReport:
    """Observability report for a strip operation."""

    tool_name: str
    was_write_tool: bool
    tokens_found: int
    tokens_stripped: int
    skipped: bool
    skip_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 4. Callable validators
# ---------------------------------------------------------------------------


def is_write_tool(tool_name: str, exclude_tools: FrozenSet[str]) -> bool:
    """Check if tool_name is in the write-tools exclusion set.

    PRE-IS-1: tool_name is a string (caller responsibility; raises TypeError if not)
    POST-IS-1: returns True if tool_name (case-insensitive) is in exclude_tools
    """
    if not isinstance(tool_name, str):
        return False
    return (
        tool_name in exclude_tools
        or tool_name.lower() in {t.lower() for t in exclude_tools}
    )


def walk_and_strip(value: Any) -> tuple[Any, int]:
    """Recursively walk a JSON value and strip CCR tokens from all strings.

    PRE-WALK-1: value is a JSON-compatible type (str, int, float, bool, None, list, dict)
    POST-WALK-1: returns (sanitized_value, tokens_stripped)
    POST-WALK-2: all string values have CCR tokens replaced with empty string
    INV-WALK-1: non-string values are returned unchanged
    """
    if isinstance(value, str):
        if "<<ccr:" not in value:
            return value, 0
        matches = CCR_TOKEN_RE.findall(value)
        if not matches:
            return value, 0
        sanitized = CCR_TOKEN_RE.sub("", value)
        return sanitized, len(matches)
    elif isinstance(value, dict):
        sanitized_dict: Dict[str, Any] = {}
        total_stripped = 0
        for k, v in value.items():
            new_v, stripped = walk_and_strip(v)
            sanitized_dict[k] = new_v
            total_stripped += stripped
        return sanitized_dict, total_stripped
    elif isinstance(value, list):
        sanitized_list: List[Any] = []
        total_stripped = 0
        for item in value:
            new_item, stripped = walk_and_strip(item)
            sanitized_list.append(new_item)
            total_stripped += stripped
        return sanitized_list, total_stripped
    else:
        # int, float, bool, None — pass through unchanged (INV-WALK-1)
        return value, 0


def validate_strip_ccr_from_tool_input(
    tool_name: Any,
    input_json: Any,
    exclude_tools: Any = None,
) -> StripResult:
    """Validate inputs and strip CCR tokens from tool_use parameters.

    This is the contract validator — raises on PRE violations, returns
    StripResult on success. Callable by tests and production code.

    PRE-STRIP-1: tool_name is a non-empty string
    PRE-STRIP-2: input_json is a dict
    PRE-STRIP-3: exclude_tools is a set/frozenset or None
    """
    if not isinstance(tool_name, str) or not tool_name:
        raise InvalidToolNameError(tool_name)
    if not isinstance(input_json, dict):
        raise InvalidInputJSONError(input_json)
    if exclude_tools is not None and not isinstance(exclude_tools, (set, frozenset)):
        raise InvalidExcludeSetError(exclude_tools)
    effective_exclude: Optional[FrozenSet[str]] = (
        frozenset(exclude_tools) if exclude_tools is not None else None
    )
    return strip_ccr_from_tool_input(tool_name, input_json, effective_exclude)


def strip_ccr_from_tool_input(
    tool_name: str,
    input_json: Dict[str, Any],
    exclude_tools: Optional[FrozenSet[str]] = None,
) -> StripResult:
    """Strip CCR tokens from tool_use input parameters for write tools.

    This is the primary contract function. It checks whether the tool is a
    write tool, and if so, walks the entire input JSON tree to strip CCR
    tokens from all string values.

    PRE-STRIP-1: tool_name is a non-empty string
    PRE-STRIP-2: input_json is a dict
    PRE-STRIP-3: exclude_tools is a set/frozenset or None (None uses DEFAULT_WRITE_TOOLS)
    POST-STRIP-1: returns StripResult with sanitized_input containing no CCR tokens
                  (for write tools)
    POST-STRIP-2: for non-write tools, sanitized_input == input_json (unchanged)
    POST-STRIP-3: tokens_found >= tokens_stripped (always)
    POST-STRIP-4: was_stripped == True iff tokens_stripped > 0
    INV-STRIP-1: tool_name in result == tool_name in input (unchanged)
    INV-STRIP-2: non-CCR content in string values is preserved exactly
    INV-STRIP-3: result.tool_name == tool_name (always)
    ERRORS-STRIP-1: raises InvalidToolNameError if tool_name is not a non-empty string
    ERRORS-STRIP-2: raises InvalidInputJSONError if input_json is not a dict
    FORBIDDEN-STRIP-1: CCR tokens MUST NOT appear in sanitized_input for write tools
    FORBIDDEN-STRIP-2: non-CCR content MUST NOT be modified in sanitized_input
    FORBIDDEN-STRIP-3: non-write tool input MUST NOT be modified
    """
    # PRE validation
    if not isinstance(tool_name, str) or not tool_name:
        raise InvalidToolNameError(tool_name)
    if not isinstance(input_json, dict):
        raise InvalidInputJSONError(input_json)
    if exclude_tools is not None and not isinstance(exclude_tools, (set, frozenset)):
        raise InvalidExcludeSetError(exclude_tools)

    effective_exclude = exclude_tools if exclude_tools is not None else DEFAULT_WRITE_TOOLS

    # Check if this is a write tool
    if not is_write_tool(tool_name, effective_exclude):
        # FORBIDDEN-STRIP-3: non-write tool input unchanged
        return StripResult(
            tool_name=tool_name,
            sanitized_input=input_json,
            tokens_found=0,
            tokens_stripped=0,
            was_stripped=False,
        )

    # Walk and strip CCR tokens from all string values
    sanitized, tokens_stripped = walk_and_strip(input_json)

    # Count tokens in original for reporting
    import json as _json
    original_str = _json.dumps(input_json)
    tokens_found = len(CCR_TOKEN_RE.findall(original_str))

    return StripResult(
        tool_name=tool_name,
        sanitized_input=sanitized,
        tokens_found=tokens_found,
        tokens_stripped=tokens_stripped,
        was_stripped=tokens_stripped > 0,
    )


# ---------------------------------------------------------------------------
# 5. CONTRACT_* traceability dicts
# ---------------------------------------------------------------------------

STRIP_CONTRACT = {
    "PRE-STRIP-1": "tool_name MUST be a non-empty string",
    "PRE-STRIP-2": "input_json MUST be a dict (JSON object)",
    "PRE-STRIP-3": "exclude_tools MUST be a set/frozenset or None",
    "POST-STRIP-1": "sanitized_input for write tools contains no <<ccr:HASH...>> tokens",
    "POST-STRIP-2": "non-write tool input passes through unchanged",
    "POST-STRIP-3": "tokens_found >= tokens_stripped (always)",
    "POST-STRIP-4": "was_stripped == True iff tokens_stripped > 0",
    "INV-STRIP-1": "tool_name preserved in result (unchanged)",
    "INV-STRIP-2": "non-CCR content in string values preserved exactly",
    "INV-STRIP-3": "result.tool_name == tool_name",
    "ERRORS-STRIP-1": "InvalidToolNameError if tool_name is not a non-empty string",
    "ERRORS-STRIP-2": "InvalidInputJSONError if input_json is not a dict",
    "ERRORS-STRIP-3": "StripFailedError if exception during strip — fail-open, forward tool_use unchanged",
    "FORBIDDEN-STRIP-1": "CCR tokens MUST NOT appear in sanitized_input for write tools",
    "FORBIDDEN-STRIP-2": "non-CCR content MUST NOT be modified",
    "FORBIDDEN-STRIP-3": "non-write tool input MUST NOT be modified",
}

WRITE_TOOLS_CONTRACT = {
    "POST-IS-1": "is_write_tool returns True if tool_name in exclude_tools (case-insensitive)",
    "DEFAULT-1": "DEFAULT_WRITE_TOOLS includes memory.remember, memory.delete, Write, Edit, "
                 "mcp__memory__memory_remember, mcp__memory__memory_delete",
}

WALK_CONTRACT = {
    "PRE-WALK-1": "value is JSON-compatible type (str, int, float, bool, None, list, dict)",
    "POST-WALK-1": "returns (sanitized_value, tokens_stripped) tuple",
    "POST-WALK-2": "all string values have CCR tokens replaced with empty string",
    "INV-WALK-1": "non-string values returned unchanged",
}

TRACEABILITY_MATRIX = {
    "REQ-2026-CCR-STRIP": [
        "PRE-STRIP-1", "PRE-STRIP-2", "PRE-STRIP-3",
        "POST-STRIP-1", "POST-STRIP-2", "POST-STRIP-3", "POST-STRIP-4",
        "INV-STRIP-1", "INV-STRIP-2", "INV-STRIP-3",
        "ERRORS-STRIP-1", "ERRORS-STRIP-2", "ERRORS-STRIP-3",
        "FORBIDDEN-STRIP-1", "FORBIDDEN-STRIP-2", "FORBIDDEN-STRIP-3",
    ],
    "INV-01": ["FORBIDDEN-STRIP-1"],
    "INV-02": ["POST-STRIP-2", "FORBIDDEN-STRIP-3"],
    "INV-03": ["INV-STRIP-2", "FORBIDDEN-STRIP-2"],
    "INV-04": ["ERRORS-STRIP-3"],  # Fail-open: forward unchanged on exception
    "INV-05": ["CCR_TOKEN_PATTERN"],
    "INV-06": ["POST-WALK-2"],
}
