"""
Unit tests for Magic Number detection.

What these tests enforce:
1. Scan for numeric literals anywhere in the code.
2. Exclude literals that are part of constant definitions OR known safe literals.
3. Classify remaining literals by context.
4. Ensure emitted context_type exists in the rule registry (rules.py).

"""

import pytest
import sys

from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.violations.detect_magic_numbers import detect_magic_numbers
from src.violations.rules import RULES, get_rule


def _run(code: str, *, language: str = "generic"):
    return detect_magic_numbers(code, language=language)


def _contexts(violations):
    return [getattr(v, "context_type", None) for v in violations]


def _literals(violations):
    return [getattr(v, "literal", None) for v in violations]


# =====================================================================
# Registry sanity
# =====================================================================

def test_all_emitted_context_types_exist_in_rule_registry():
    code = "\n".join(
        [
            "x = request.get(url, 10)",
            "if (x > 37) { ok(); }",
            "for i in range(12): pass",
            "timeout = 10",
        ]
    ) + "\n"

    violations = _run(code, language="generic")

    for ctx in _contexts(violations):
        assert ctx is not None
        assert ctx in RULES, f"Unknown context_type emitted: {ctx}"
        assert get_rule(ctx).rule_id == ctx


# =====================================================================
# POSITIVE CASES (+): should be detected as magic numbers
# =====================================================================

def test_detects_call_argument_even_with_equals_present():
    code = "x = request.get(url, 10)\n"
    violations = _run(code, language="python")

    assert "CALL_ARG" in _contexts(violations)
    assert "10" in _literals(violations)


def test_detects_threshold_comparison():
    code = "if (x > 37) { doSomething(); }\n"
    violations = _run(code, language="java")

    assert "THRESHOLD" in _contexts(violations)
    assert "37" in _literals(violations)


def test_detects_loop_bound():
    code = "for i in range(12):\n    pass\n"
    violations = _run(code, language="python")

    assert "LOOP_BOUND" in _contexts(violations)
    assert "12" in _literals(violations)


def test_detects_assignment_rhs_literal():
    code = "timeout = 10\n"
    violations = _run(code, language="python")

    assert "ASSIGNMENT" in _contexts(violations)
    assert "10" in _literals(violations)


# =====================================================================
# NEGATIVE CASES (-): should NOT be detected as magic numbers
# =====================================================================

def test_does_not_flag_js_ts_const_definition():
    code = "const TIMEOUT_SECONDS = 10;\n"
    violations = _run(code, language="javascript")
    assert len(violations) == 0


def test_does_not_flag_java_final_definition():
    code = "final double PI = 3.14;\n"
    violations = _run(code, language="java")
    assert len(violations) == 0


def test_does_not_flag_cpp_define_constant():
    code = "#define PI 3.14\n"
    violations = _run(code, language="cpp")
    assert len(violations) == 0


def test_does_not_flag_cpp_constexpr_constant():
    code = "constexpr int MAX_USERS = 100;\n"
    violations = _run(code, language="cpp")
    assert len(violations) == 0


def test_does_not_flag_swift_let_definition():
    code = "let pi = 3.14\n"
    violations = _run(code, language="swift")
    assert len(violations) == 0


def test_does_not_flag_kotlin_val_definition():
    code = "val pi = 3.14\n"
    violations = _run(code, language="kotlin")
    assert len(violations) == 0


def test_does_not_flag_python_all_caps_constant_convention():
    code = "PI = 3.14\n"
    violations = _run(code, language="python")
    assert len(violations) == 0


def test_does_not_flag_math_pi_safe_named_constant():
    code = "area = r * r * math.pi\n"
    violations = _run(code, language="python")
    assert len(violations) == 0


def test_does_not_flag_php_define_constant():
    code = 'define("PI", 3.14);\n'
    violations = _run(code, language="php")
    assert len(violations) == 0


def test_does_not_flag_safe_literal_zero_one_basic():
    code = "for i in range(0, n):\n    x = x + 1\n"
    violations = _run(code, language="python")

    # It is okay if other literals are detected, but 0 and 1 must not be reported.
    for lit in _literals(violations):
        assert lit not in ("0", "1")
