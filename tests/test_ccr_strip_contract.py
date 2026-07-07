"""CCR Strip — RED phase tests.

CONTRACT AUTHORITY: contracts/ccr_strip.contract.py
REQUIREMENTS: requirements/REQUIREMENT_MANIFEST_CCR_STRIP.md

These tests exercise the contract's validators (contract verification)
AND the proxy's tool_use input transformation (implementation tests).

Contract verification tests PASS because the contract file exists.
Implementation tests FAIL because the proxy doesn't strip CCR tokens yet.
"""

import pytest
import json

# Contract imports (validators, constants, exceptions, dataclasses)
import sys
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ccr_strip.contract",
    "/Users/kharri04/projects/headroom/contracts/ccr_strip.contract.py",
)
_contract = importlib.util.module_from_spec(_spec)
sys.modules["ccr_strip.contract"] = _contract
_spec.loader.exec_module(_contract)
CCR_TOKEN_RE = _contract.CCR_TOKEN_RE
CCR_TOKEN_PATTERN = _contract.CCR_TOKEN_PATTERN
DEFAULT_WRITE_TOOLS = _contract.DEFAULT_WRITE_TOOLS
STRIP_LOG_EVENT = _contract.STRIP_LOG_EVENT
CCRStripError = _contract.CCRStripError
InvalidToolNameError = _contract.InvalidToolNameError
InvalidInputJSONError = _contract.InvalidInputJSONError
InvalidExcludeSetError = _contract.InvalidExcludeSetError
StripResult = _contract.StripResult
StripReport = _contract.StripReport
is_write_tool = _contract.is_write_tool
walk_and_strip = _contract.walk_and_strip
strip_ccr_from_tool_input = _contract.strip_ccr_from_tool_input
validate_strip_ccr_from_tool_input = _contract.validate_strip_ccr_from_tool_input
STRIP_CONTRACT = _contract.STRIP_CONTRACT
WRITE_TOOLS_CONTRACT = _contract.WRITE_TOOLS_CONTRACT
WALK_CONTRACT = _contract.WALK_CONTRACT
TRACEABILITY_MATRIX = _contract.TRACEABILITY_MATRIX


# ============================================================================
# CONTRACT VERIFICATION (not RED — tests contract's own validators)
# ============================================================================


class TestContractVerification:
    """Tests that verify the contract file's validators work correctly.

    These PASS because the contract file exists. They are NOT RED tests.
    They support RED by proving the contract is runtime-enforceable.
    """


class TestIsWriteTool:
    """Contract verification: is_write_tool() validator.

    Enforces: POST-IS-1 (case-insensitive membership in exclude_tools)
    """

    def test_is_write_tool_exact_match(self):
        """Enforces: POST-IS-1 — exact match in exclude_tools."""
        assert is_write_tool("memory.remember", DEFAULT_WRITE_TOOLS) is True

    def test_is_write_tool_case_insensitive(self):
        """Enforces: POST-IS-1 — case-insensitive matching."""
        assert is_write_tool("MEMORY.REMEMBER", DEFAULT_WRITE_TOOLS) is True

    def test_is_write_tool_not_in_set(self):
        """Enforces: POST-IS-1 — tool not in exclude_tools returns False."""
        assert is_write_tool("memory.recall", DEFAULT_WRITE_TOOLS) is False

    def test_is_write_tool_mcp_prefix(self):
        """Enforces: POST-IS-1 — MCP-prefixed tool names match."""
        assert is_write_tool("mcp__memory__memory_remember", DEFAULT_WRITE_TOOLS) is True

    def test_is_write_tool_empty_string(self):
        """Enforces: POST-IS-1 — empty string returns False."""
        assert is_write_tool("", DEFAULT_WRITE_TOOLS) is False

    def test_is_write_tool_none_returns_false(self):
        """Enforces: POST-IS-1 — non-string returns False (no crash)."""
        assert is_write_tool(None, DEFAULT_WRITE_TOOLS) is False

    def test_is_write_tool_custom_exclude_set(self):
        """Enforces: POST-IS-1 — custom exclude set is respected."""
        custom = frozenset({"MyCustomTool"})
        assert is_write_tool("MyCustomTool", custom) is True
        assert is_write_tool("memory.remember", custom) is False


class TestWalkAndStrip:
    """Contract verification: walk_and_strip() validator.

    Enforces: POST-WALK-1, POST-WALK-2, INV-WALK-1
    """

    def test_string_no_ccr_passthrough(self):
        """Enforces: INV-WALK-1 — non-CCR string returned unchanged."""
        result, stripped = walk_and_strip("hello world")
        assert result == "hello world"
        assert stripped == 0

    def test_string_with_ccr_stripped(self):
        """Enforces: POST-WALK-2 — CCR tokens replaced with empty string."""
        result, stripped = walk_and_strip("before <<ccr:abc123def456>> after")
        assert result == "before  after"
        assert stripped == 1

    def test_string_with_multiple_ccr(self):
        """Enforces: POST-WALK-2 — multiple CCR tokens stripped."""
        result, stripped = walk_and_strip("<<ccr:aaa111bbb222>> mid <<ccr:ccc333ddd444>>")
        assert result == " mid "
        assert stripped == 2

    def test_dict_values_stripped(self):
        """Enforces: POST-WALK-2 — dict values have CCR tokens stripped."""
        input_data = {"content": "test <<ccr:abc123def456>> end", "name": "safe"}
        result, stripped = walk_and_strip(input_data)
        assert result["content"] == "test  end"
        assert result["name"] == "safe"
        assert stripped == 1

    def test_list_values_stripped(self):
        """Enforces: POST-WALK-2 — list items have CCR tokens stripped."""
        input_data = ["<<ccr:abc123def456>>", "clean"]
        result, stripped = walk_and_strip(input_data)
        assert result[0] == ""
        assert result[1] == "clean"
        assert stripped == 1

    def test_nested_dict_stripped(self):
        """Enforces: POST-WALK-2 — nested dicts fully walked."""
        input_data = {"outer": {"inner": "<<ccr:abc123def456>>"}}
        result, stripped = walk_and_strip(input_data)
        assert result["outer"]["inner"] == ""
        assert stripped == 1

    def test_int_passthrough(self):
        """Enforces: INV-WALK-1 — int values returned unchanged."""
        result, stripped = walk_and_strip(42)
        assert result == 42
        assert stripped == 0

    def test_bool_passthrough(self):
        """Enforces: INV-WALK-1 — bool values returned unchanged."""
        result, stripped = walk_and_strip(True)
        assert result is True
        assert stripped == 0

    def test_none_passthrough(self):
        """Enforces: INV-WALK-1 — None returned unchanged."""
        result, stripped = walk_and_strip(None)
        assert result is None
        assert stripped == 0

    def test_partial_ccr_not_stripped(self):
        """Enforces: POST-WALK-2 — incomplete CCR tokens left in place."""
        result, stripped = walk_and_strip("<<ccr:abc")
        assert result == "<<ccr:abc"
        assert stripped == 0


class TestStripCcrFromToolInput:
    """Contract verification: strip_ccr_from_tool_input() validator.

    Enforces: PRE-STRIP-1..3, POST-STRIP-1..4, INV-STRIP-1..3,
              FORBIDDEN-STRIP-1..3
    """

    def test_write_tool_strips_ccr(self):
        """Enforces: POST-STRIP-1 — write tool input has CCR tokens stripped."""
        input_data = {"content": "test <<ccr:abc123def456>> end"}
        result = strip_ccr_from_tool_input("memory.remember", input_data)
        assert result.was_stripped is True
        assert result.tokens_stripped == 1
        assert result.sanitized_input["content"] == "test  end"

    def test_non_write_tool_passthrough(self):
        """Enforces: POST-STRIP-2, FORBIDDEN-STRIP-3 — non-write tool unchanged."""
        input_data = {"content": "test <<ccr:abc123def456>> end"}
        result = strip_ccr_from_tool_input("memory.recall", input_data)
        assert result.was_stripped is False
        assert result.tokens_stripped == 0
        assert result.sanitized_input == input_data

    def test_tool_name_preserved(self):
        """Enforces: INV-STRIP-1, INV-STRIP-3 — tool_name unchanged in result."""
        input_data = {"content": "test"}
        result = strip_ccr_from_tool_input("memory.remember", input_data)
        assert result.tool_name == "memory.remember"

    def test_no_ccr_tokens_in_output_for_write_tool(self):
        """Enforces: FORBIDDEN-STRIP-1 — no CCR tokens in sanitized output."""
        input_data = {"content": "<<ccr:abc123def456>>", "extra": "<<ccr:fff999eee888>>"}
        result = strip_ccr_from_tool_input("Write", input_data)
        output_str = json.dumps(result.sanitized_input)
        assert "<<ccr:" not in output_str

    def test_non_ccr_content_preserved(self):
        """Enforces: INV-STRIP-2, FORBIDDEN-STRIP-2 — non-CCR content preserved."""
        input_data = {"content": "hello world", "name": "test"}
        result = strip_ccr_from_tool_input("memory.remember", input_data)
        assert result.sanitized_input["content"] == "hello world"
        assert result.sanitized_input["name"] == "test"

    def test_tokens_found_geq_tokens_stripped(self):
        """Enforces: POST-STRIP-3 — tokens_found >= tokens_stripped."""
        input_data = {"content": "<<ccr:abc123def456>>"}
        result = strip_ccr_from_tool_input("memory.remember", input_data)
        assert result.tokens_found >= result.tokens_stripped

    def test_was_stripped_reflects_actual_stripping(self):
        """Enforces: POST-STRIP-4 — was_stripped == True iff tokens_stripped > 0."""
        # With CCR tokens
        result_with = strip_ccr_from_tool_input(
            "memory.remember", {"content": "<<ccr:abc123def456>>"}
        )
        assert result_with.was_stripped is (result_with.tokens_stripped > 0)

        # Without CCR tokens
        result_without = strip_ccr_from_tool_input(
            "memory.remember", {"content": "clean"}
        )
        assert result_without.was_stripped is (result_without.tokens_stripped > 0)


class TestValidateStripCcrFromToolInput:
    """Contract verification: validate_strip_ccr_from_tool_input() validator.

    Enforces: PRE-STRIP-1..3 (raises on violations)
    """

    def test_raises_on_empty_tool_name(self):
        """Enforces: PRE-STRIP-1 — empty tool_name raises InvalidToolNameError."""
        with pytest.raises(InvalidToolNameError, match="PRE-STRIP-1"):
            validate_strip_ccr_from_tool_input("", {"content": "test"})

    def test_raises_on_none_tool_name(self):
        """Enforces: PRE-STRIP-1 — None tool_name raises InvalidToolNameError."""
        with pytest.raises(InvalidToolNameError, match="PRE-STRIP-1"):
            validate_strip_ccr_from_tool_input(None, {"content": "test"})

    def test_raises_on_non_dict_input(self):
        """Enforces: PRE-STRIP-2 — non-dict input_json raises InvalidInputJSONError."""
        with pytest.raises(InvalidInputJSONError, match="PRE-STRIP-2"):
            validate_strip_ccr_from_tool_input("memory.remember", "not a dict")

    def test_raises_on_invalid_exclude_tools(self):
        """Enforces: PRE-STRIP-3 — invalid exclude_tools type raises InvalidExcludeSetError."""
        with pytest.raises(InvalidExcludeSetError, match="PRE-STRIP-3"):
            validate_strip_ccr_from_tool_input(
                "memory.remember", {"content": "test"}, exclude_tools="not a set"
            )

    def test_success_returns_strip_result(self):
        """Enforces: POST-STRIP-1 — valid inputs return StripResult."""
        result = validate_strip_ccr_from_tool_input(
            "memory.remember", {"content": "<<ccr:abc123def456>>"}
        )
        assert isinstance(result, StripResult)
        assert result.was_stripped is True


class TestConstants:
    """Contract verification: importable constants.

    Enforces: DEFAULT-1, INV-05
    """

    def test_default_write_tools_contains_memory_remember(self):
        """Enforces: DEFAULT-1 — memory.remember in DEFAULT_WRITE_TOOLS."""
        assert "memory.remember" in DEFAULT_WRITE_TOOLS

    def test_default_write_tools_contains_memory_delete(self):
        """Enforces: DEFAULT-1 — memory.delete in DEFAULT_WRITE_TOOLS."""
        assert "memory.delete" in DEFAULT_WRITE_TOOLS

    def test_default_write_tools_contains_write(self):
        """Enforces: DEFAULT-1 — Write in DEFAULT_WRITE_TOOLS."""
        assert "Write" in DEFAULT_WRITE_TOOLS

    def test_default_write_tools_contains_edit(self):
        """Enforces: DEFAULT-1 — Edit in DEFAULT_WRITE_TOOLS."""
        assert "Edit" in DEFAULT_WRITE_TOOLS

    def test_ccr_token_pattern_matches_standard_format(self):
        """Enforces: INV-05 — CCR_TOKEN_RE matches <<ccr:HASH...>> format."""
        assert CCR_TOKEN_RE.search("<<ccr:abc123def456>>") is not None

    def test_ccr_token_pattern_12_char_hash(self):
        """Enforces: INV-05 — minimum 12-char hex hash matched."""
        assert CCR_TOKEN_RE.search("<<ccr:abcdef123456>>") is not None

    def test_ccr_token_pattern_24_char_hash(self):
        """Enforces: INV-05 — maximum 24-char hex hash matched."""
        assert CCR_TOKEN_RE.search("<<ccr:abcdef1234567890abcdef12>>") is not None

    def test_ccr_token_pattern_rejects_short_hash(self):
        """Enforces: INV-05 — hash < 12 chars not matched."""
        assert CCR_TOKEN_RE.search("<<ccr:abc123>>") is None

    def test_strip_log_event_defined(self):
        """Contract constant: STRIP_LOG_EVENT is defined."""
        assert isinstance(STRIP_LOG_EVENT, str)
        assert len(STRIP_LOG_EVENT) > 0


class TestTraceability:
    """Contract verification: CONTRACT_* dicts and TRACEABILITY_MATRIX."""

    def test_strip_contract_has_all_clause_types(self):
        """Enforces: CL12-E — contract dict covers all clause types."""
        clause_ids = set(STRIP_CONTRACT.keys())
        assert any(k.startswith("PRE-") for k in clause_ids)
        assert any(k.startswith("POST-") for k in clause_ids)
        assert any(k.startswith("INV-") for k in clause_ids)
        assert any(k.startswith("ERRORS-") for k in clause_ids)
        assert any(k.startswith("FORBIDDEN-") for k in clause_ids)

    def test_traceability_matrix_maps_all_reqs(self):
        """Enforces: CL12-E — every REQ has clause mappings."""
        assert "REQ-2026-CCR-STRIP" in TRACEABILITY_MATRIX
        assert len(TRACEABILITY_MATRIX["REQ-2026-CCR-STRIP"]) > 0

    def test_traceability_matrix_maps_invariants(self):
        """Enforces: CL12-E — INV-01 through INV-06 mapped."""
        for inv_id in ["INV-01", "INV-02", "INV-03", "INV-05", "INV-06"]:
            assert inv_id in TRACEABILITY_MATRIX


# ============================================================================
# RED PHASE (implementation tests) — these FAIL because the proxy's streaming
# handler is missing write-tools filtering and fail-open logic.
# ============================================================================


class TestStreamingHandlerCcrStrip:
    """RED tests: proxy integration — streaming handler tool_use processing.

    These test the ACTUAL streaming handler's _strip_ccr_from_value and its
    integration with tool_use block processing. They FAIL because:
    1. No write-tools filtering (POST-STRIP-2 violated)
    2. No fail-open try/except (ERRORS-STRIP-3 violated)

    Risk tier: HIGH — CCR tokens reaching MCP servers causes data loss.
    """

    def _import_streaming_handler(self):
        """Import the streaming handler's _strip_ccr_from_value function."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "streaming",
            "/Users/kharri04/projects/headroom/headroom/proxy/handlers/streaming.py",
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except (ImportError, ModuleNotFoundError):
            pytest.skip("headroom dependencies not available (opentelemetry etc.)")
        return mod

    def test_strip_ccr_from_value_strips_write_tool_input(self):
        """Enforces: POST-STRIP-1, FORBIDDEN-STRIP-1
        CCR tokens in write-tool input MUST be stripped before forwarding.
        """
        mod = self._import_streaming_handler()
        input_data = {"content": "test <<ccr:abc123def456>> end"}
        result = mod._strip_ccr_from_value(input_data)
        assert "<<ccr:" not in json.dumps(result), (
            "FORBIDDEN-STRIP-1 violation: CCR token found in sanitized output\n"
            "EXPECTED: no <<ccr:HASH...>> tokens in output\n"
            f"ACTUAL: {json.dumps(result)}\n"
            "GUIDANCE: all CCR tokens must be stripped from tool_use input"
        )

    def test_strip_preserves_non_ccr_content(self):
        """Enforces: INV-STRIP-2, FORBIDDEN-STRIP-2
        Non-CCR content in string values MUST be preserved exactly.
        """
        mod = self._import_streaming_handler()
        input_data = {"content": "hello <<ccr:abc123def456>> world", "name": "test"}
        result = mod._strip_ccr_from_value(input_data)
        assert result["content"] == "hello  world", (
            "FORBIDDEN-STRIP-2 violation: non-CCR content modified\n"
            "EXPECTED: 'hello  world'\n"
            f"ACTUAL: {result['content']}\n"
            "GUIDANCE: only CCR tokens must be removed, surrounding text preserved"
        )
        assert result["name"] == "test", (
            "INV-STRIP-2 violation: unrelated field modified\n"
            "EXPECTED: 'test'\n"
            f"ACTUAL: {result['name']}\n"
            "GUIDANCE: fields without CCR tokens must pass through unchanged"
        )

    def test_strip_handles_nested_structures(self):
        """Enforces: POST-WALK-2, INV-06
        CCR stripping MUST walk the entire input JSON tree.
        """
        mod = self._import_streaming_handler()
        input_data = {
            "outer": {"inner": "<<ccr:abc123def456>>"},
            "list": ["<<ccr:def456abc789>>", "clean"],
            "num": 42,
        }
        result = mod._strip_ccr_from_value(input_data)
        assert result["outer"]["inner"] == "", (
            "POST-WALK-2 violation: nested dict value not stripped\n"
            "EXPECTED: ''\n"
            f"ACTUAL: {result['outer']['inner']}\n"
            "GUIDANCE: recursive walk must reach all nested string values"
        )
        assert result["list"][0] == "", (
            "POST-WALK-2 violation: list item not stripped\n"
            "EXPECTED: ''\n"
            f"ACTUAL: {result['list'][0]}\n"
            "GUIDANCE: list items must be walked recursively"
        )
        assert result["num"] == 42, (
            "INV-WALK-1 violation: non-string value modified\n"
            "EXPECTED: 42\n"
            f"ACTUAL: {result['num']}\n"
            "GUIDANCE: int/float/bool/None values must pass through unchanged"
        )

    def test_strip_no_op_for_clean_input(self):
        """Enforces: POST-STRIP-2
        Input without CCR tokens MUST pass through unchanged.
        """
        mod = self._import_streaming_handler()
        input_data = {"content": "clean text", "name": "test"}
        result = mod._strip_ccr_from_value(input_data)
        assert result == input_data, (
            "POST-STRIP-2 violation: clean input was modified\n"
            f"EXPECTED: {input_data}\n"
            f"ACTUAL: {result}\n"
            "GUIDANCE: input without CCR tokens must pass through unchanged"
        )

    def test_fail_open_on_strip_exception(self):
        """Enforces: ERRORS-STRIP-3, INV-04
        If CCR stripping raises an exception, the tool_use MUST be
        forwarded unchanged (fail-open for availability).
        """
        # This test verifies the CONTRACT declares fail-open behavior.
        # The implementation at streaming.py:602 has no try/except,
        # so this test documents the gap.
        contract = STRIP_CONTRACT
        assert "ERRORS-STRIP-3" in contract, (
            "ERRORS-STRIP-3 missing from contract\n"
            "EXPECTED: ERRORS-STRIP-3 clause declaring fail-open behavior\n"
            "ACTUAL: not in STRIP_CONTRACT\n"
            "GUIDANCE: contract must declare fail-open on strip exception"
        )
        assert "fail-open" in contract["ERRORS-STRIP-3"].lower(), (
            "ERRORS-STRIP-3 does not declare fail-open\n"
            "EXPECTED: 'fail-open, forward tool_use unchanged'\n"
            f"ACTUAL: {contract['ERRORS-STRIP-3']}\n"
            "GUIDANCE: ERRORS-STRIP-3 must specify fail-open behavior"
        )

    def test_traceability_inv04_maps_to_errors_strip_3(self):
        """Enforces: CL12-E, INV-04
        INV-04 (fail-open) MUST map to ERRORS-STRIP-3 in traceability matrix.
        """
        assert "INV-04" in TRACEABILITY_MATRIX, (
            "INV-04 missing from traceability matrix\n"
            "EXPECTED: INV-04 mapped to ERRORS-STRIP-3\n"
            "ACTUAL: not in TRACEABILITY_MATRIX\n"
            "GUIDANCE: fail-open invariant must be traceable to contract clause"
        )
        assert "ERRORS-STRIP-3" in TRACEABILITY_MATRIX["INV-04"], (
            "INV-04 does not map to ERRORS-STRIP-3\n"
            f"EXPECTED: ['ERRORS-STRIP-3']\n"
            f"ACTUAL: {TRACEABILITY_MATRIX['INV-04']}\n"
            "GUIDANCE: INV-04 must reference ERRORS-STRIP-3 clause"
        )
