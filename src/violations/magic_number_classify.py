"""
Magic Number Detector — Context Classification 
====================================================

Purpose
-------
This module classifies detected numeric literals based on the logical
context in which they appear. After numeric literals are identified
and masking/filtering has been applied, this layer determines whether
a number is used in a meaningful program-logic scenario.

Context Categories
------------------
Each numeric literal is classified into one of the following categories:

    • LOOP_BOUND  — Used in loop constructs
                     (for-loops, while-loops, Python range())

    • THRESHOLD   — Used in comparison expressions
                     (e.g., if (x > 7))

    • CALL_ARG    — Used as a function or method argument
                     (e.g., retry(5))

    • ASSIGNMENT  — Assigned directly to a variable
                     (e.g., timeout = 30)

    • GENERIC     — Detected but does not match a specific
                     logical category
"""

from __future__ import annotations

import re
from typing import Tuple

# Comparison operators
RX_COMPARISON_OP = r"(<=|>=|===|!==|==|!=|<|>)"
COMPARISON_OP_RE = re.compile(RX_COMPARISON_OP)

# Assignment operator
RX_ASSIGNMENT = r"(^|[^=!<>])=([^=]|$)"
ASSIGNMENT_RE = re.compile(RX_ASSIGNMENT)

# Function call 
RX_CALL_LIKE_JS = r"[A-Za-z_$][\w$]*\s*\("
RX_CALL_LIKE_PY = r"[A-Za-z_]\w*\s*\("
RX_CALL_LIKE_JAVA = r"[A-Za-z_$][\w$]*\s*\("

CALL_LIKE_JS_RE = re.compile(RX_CALL_LIKE_JS)
CALL_LIKE_PY_RE = re.compile(RX_CALL_LIKE_PY)
CALL_LIKE_JAVA_RE = re.compile(RX_CALL_LIKE_JAVA)

# Python: range(...) for loop bounds
RX_PY_RANGE_CALL = r"\brange\s*\("
PY_RANGE_RE = re.compile(RX_PY_RANGE_CALL)


def classify_context(lang: str, line_sanitized: str, num_span: Tuple[int, int]) -> str:
    """
    Classify the context where a number appears.

    Categories:
      - LOOP_BOUND: for loops, while loops, range()
      - THRESHOLD: comparisons
      - CALL_ARG: function arguments
      - ASSIGNMENT: variable assignments
      - GENERIC: other uses
    """
    start, end = num_span
    before = line_sanitized[:start]
    after = line_sanitized[end:]

    # Check for loop bounds
    if re.search(r"\bfor\s*\(", line_sanitized):
        # JS/TS/Java: for(...) loops
        return "LOOP_BOUND"

    if lang == "python" and PY_RANGE_RE.search(line_sanitized):
        # Python: range(...) calls
        return "LOOP_BOUND"

    if re.search(r"\bwhile\b", line_sanitized) and COMPARISON_OP_RE.search(line_sanitized):
        # while loops with conditions
        return "LOOP_BOUND"

    # Check for comparisons
    if COMPARISON_OP_RE.search(line_sanitized):
        return "THRESHOLD"

    # Check for function call arguments
    if lang in {"javascript", "typescript"}:
        if CALL_LIKE_JS_RE.search(before) and (")" in after or "," in after):
            return "CALL_ARG"
    elif lang == "python":
        if CALL_LIKE_PY_RE.search(before) and (")" in after or "," in after):
            return "CALL_ARG"
    elif lang == "java":
        if CALL_LIKE_JAVA_RE.search(before) and (")" in after or "," in after):
            return "CALL_ARG"

    # Check for assignments
    if ASSIGNMENT_RE.search(line_sanitized):
        return "ASSIGNMENT"

    return "GENERIC"