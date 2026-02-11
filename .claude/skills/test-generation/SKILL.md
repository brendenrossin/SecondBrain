---
name: test-generation
description: Generates unit and integration tests for substantive functions during development. Use this skill when creating or significantly modifying functions that contain business logic, branching, error handling, or external interactions. Do NOT use for trivial helpers, simple wrappers, or functions that are correct by inspection.
argument-hint: "[module or function name]"
---

# Test Generation

Generate focused, high-coverage tests for functions that contain real logic. This skill enforces a quality bar: only test what matters, skip what does not.

## When to Write Tests

Write tests when creating or significantly modifying functions that have:

- **Business logic** -- decision branching, non-trivial transformations, state changes
- **External interactions** -- APIs, databases, file I/O, network calls
- **Multiple code paths** -- error handling, edge cases, conditional behavior
- **Interface contracts** -- public/exported functions that other modules depend on
- **Downstream risk** -- a bug here would cause real problems elsewhere

## When NOT to Write Tests

Do NOT generate tests for:

- Simple getters/setters or thin wrappers with no logic
- One-line helpers that merely delegate to another function
- Struct/type definitions, constants, or pure configuration
- Dependency wiring or composition root functions
- Functions that are trivially correct by inspection (e.g., `return a + b`)

**Decision rule:** "Could a bug in this function go unnoticed and cause real problems?" If yes, write tests. If no, skip it.

## Instructions

1. Identify the module or function from `$ARGUMENTS` or from the current conversation context
2. Read the source file to understand the function's logic, branches, and edge cases
3. Check if a corresponding test file already exists in `tests/`
4. If the function cannot achieve full coverage without refactoring (unreachable branches, untestable dependencies), **stop and inform the user** what refactoring is needed -- do not write partial tests
5. Write tests following the project conventions below
6. Run `make check` to verify tests pass alongside lint and type checks

## Project Conventions

This project uses **pytest** with these patterns:

- **Test location:** `tests/test_{module_name}.py` (mirrors `src/secondbrain/{path}/{module}.py`)
- **Test organization:** Group related tests in classes (e.g., `class TestParseEvents:`)
- **Fixtures:** Use `tmp_path` for file I/O, patch/mock for external calls (LLM, APIs)
- **Naming:** `test_{behavior_being_tested}` -- describe what, not how
- **Helpers:** Private `_make_*` or `_create_*` helpers for test data setup
- **No docstrings on test methods** -- the test name should be self-documenting
- **One assertion focus per test** -- each test verifies one behavior or edge case

Example from the codebase:

```python
class TestParseEvents:
    def test_timed_event(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(daily_dir, "2026-02-10", "- 10:30 — Standup")
        events = _parse_events_from_file(daily_dir / "2026-02-10.md")
        assert len(events) == 1
        assert events[0].time == "10:30"
        assert events[0].title == "Standup"

    def test_empty_events_section(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(daily_dir, "2026-02-10", "")
        events = _parse_events_from_file(daily_dir / "2026-02-10.md")
        assert events == []
```

## Coverage Requirements

- Target 100% coverage of the function under test, but prioritize meaningful coverage over numbers
- Test all branches and edge cases within the function
- Include error cases and boundary conditions
- Verify both success and failure scenarios
- When evaluating coverage, only examine code within the function itself -- do not consider internals of called functions

## After Writing

- Run `make check` (lint + typecheck + tests) to verify everything passes
- Report the test count and what behaviors are covered
- Do NOT commit automatically -- let the user decide when to commit
