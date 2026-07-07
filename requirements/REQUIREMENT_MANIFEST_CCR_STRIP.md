# REQ-2026-CCR-STRIP: CCR Token Stripping from Tool Call Parameters

## CCABDD Governance

Human owns: intent (front) + reality judgment (back).
AI owns: enforcement (middle).
Neither crosses the boundary.

---

## 1. Intent Traceability
- **Source Prose**:
  > "headroom or the ai should never inject on write. ever period for any tool call"
  > "only from write tools"
  > "exclude list"
- **Our Understanding**: The headroom proxy must structurally prevent CCR tokens (`<<ccr:HASH...>>`) from appearing in outbound tool_use `input` parameters for write tools. This is a proxy-level guard, not a behavioral directive for the AI or MCP server responsibility.
- **Ambiguity Score**: 1 (clear scope, clear mechanism, clear boundary)
- **Prior Art**: Memory #9 — "feat: per-tool CCR exclusion for mc[p]" (attempted but not completed)

## 2. The Actor Matrix
| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| Headroom proxy | Intercepts, strips CCR from tool_use input | MUST NOT allow CCR tokens in write-tool parameters |
| LLM | Produces tool_use with CCR tokens (unaware) | N/A — LLM doesn't know about CCR |
| MCP servers | Execute tool calls | MUST NOT receive CCR tokens in parameters |
| CCR tokens | Exist in compressed tool results | MUST NOT propagate to tool_use input for write tools |

## 3. The State Transition
- **Initial State ($S_0$)**: LLM produces tool_use block where `input` JSON contains `<<ccr:HASH...>>` tokens (from prior compressed results)
- **Transformation**: Proxy detects CCR tokens in write-tool `input` values, replaces with empty string
- **Terminal State ($S_1$)**: MCP server receives tool_use with clean `input` — no CCR tokens, surrounding text preserved

## 3.5 Integration Specification

### Dependency Graph
[CCR strip logic] DEPENDS ON [tool_use interception in Anthropic handler] for detecting and transforming outbound tool_use blocks
[CCR strip logic] DEPENDS ON [write-tools exclusion set] for determining which tools to strip

### Control Flow Requirements
| ID | Caller | Must Invoke | Temporal Constraint | Breaks If Missing |
|----|--------|-------------|---------------------|-------------------|
| SEQ-1 | Anthropic handler (tool_use processing) | CCR strip function | BEFORE forwarding tool_use to MCP server | CCR tokens reach MCP server |
| SEQ-2 | CCR strip function | Pattern match on input JSON values | DURING tool_use processing | Tokens pass through undetected |
| SEQ-3 | CCR strip function | Write-tools exclusion check | BEFORE stripping | All tools get stripped (performance waste) |

### Integration Points Checklist
| ID | Source | Target | Handoff Data | Contract Clause |
|----|--------|--------|-------------|-----------------|
| IP-1 | LLM response (tool_use block) | Proxy handler | tool name + input JSON | SEQ-1 |
| IP-2 | Proxy handler | CCR strip function | tool name + input JSON + exclude set | SEQ-2, SEQ-3 |
| IP-3 | CCR strip function | Forwarding layer | sanitized input JSON | POST-1 |

### Lifecycle Paths
| Component | INIT | CLEANUP |
|-----------|------|---------|
| CCR strip function | Called per tool_use block | No persistent state |
| Write-tools exclusion set | Loaded from config at proxy startup | N/A (static) |

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Isolation | MCP servers SHALL NOT receive `<<ccr:HASH...>>` tokens in tool_use `input` parameters for write tools |
| INV-02 | Scope | CCR stripping SHALL apply ONLY to tools in the write-tools exclusion set |
| INV-03 | Preservation | Non-CCR content in `input` string values SHALL NOT be modified |
| INV-04 | Fail-open | If CCR stripping raises an exception, the tool_use SHALL be forwarded unchanged |
| INV-05 | Pattern | CCR pattern SHALL match `<<ccr:[a-f0-9]{12,24}\b[^>]*>>` (headroom's SmartCrusher pattern) |
| INV-06 | Depth | CCR stripping SHALL walk the entire `input` JSON tree (nested objects, arrays, strings) |

## 5. High-Entropy Zones (Adjudicated)
| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Write tool identification | How to configure which tools? | Exclude list pattern, like existing `exclude_tools` | User |
| Strip vs expand | Expand or strip? | Strip (empty string) | User |
| Scope | All tools or write only? | Only write tools | User |

## 5.5 Rejected Alternatives
| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Strip in proxy | Expand CCR tokens in MCP server | Couples every MCP server to headroom |
| Strip in proxy | Behavioral guard in CLAUDE.md (current) | Fragile — AI must remember every time |
| Exclude list | Hardcoded write-tool list | Less flexible, can't adapt to new tools |

## 6. Tool/API Interface Summary
| Interface | Purpose | Mutates State? | Called By | Triggered When |
|-----------|---------|----------------|----------|---------------|
| `strip_ccr_from_tool_input(tool_name, input_json, exclude_set)` | Remove CCR tokens from write-tool parameters | NO (returns sanitized copy) | Proxy handler | LLM produces tool_use for write tool |

## 7. Failure Mode Specification (CL15)
| Requirement | Failure Condition | Behavior | Notification |
|------------|-------------------|----------|-------------|
| CCR strip | Exception during JSON walk | FAIL-OPEN — forward tool_use unchanged | Log warning |
| CCR strip | Tool not in exclude set | PASS-THROUGH — no stripping | None |

## 8. Completion Promise
> "A tool_use block for `memory.remember` with `content='test <<ccr:abc123def456>> end'` arrives at the MCP server as `content='test  end'` — CCR token stripped, surrounding text preserved. A tool_use block for `memory.recall` with the same content passes through unchanged (not a write tool)."

## 9. Contract Authority
**Authoritative Source**: `contracts/ccr_strip.contract.py`

requirements/REQUIREMENT_MANIFEST_CCR_STRIP.md (this file)
        ↓
contracts/ccr_strip.contract.py (CL12 PRE/POST/INV/ERRORS/FORBIDDEN)
        ↓
tests/test_ccr_strip_contract.py
        ↓
headroom/proxy/handlers/anthropic.py (implementation)

## 10. Revision History
| Date | Author | Change |
|------|--------|--------|
| 2026-07-07 | Ketema Harris | Initial manifest from req-elicit |
