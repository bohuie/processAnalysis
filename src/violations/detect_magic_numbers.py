"""
Magic Number detector

Magic Number is a numeric literal value that appear in code (hard-coding parameters)
 without an explanatory name (a constant) and inside meaningful program logic.

Example of Magic Number and their classifications:
1. x = request.get(url, 10) -> CALL_ARG (a numeric literal used as a function or method argument)
2. if (strlen(pw) > 7) -> THRESHOLD (a numeric literal used in a comparison expression)
3. for i in range(12) -> LOOP BOUND (a numeric literal used to control loop iteration bounds)
4. timeout = 10 -> ASSIGNMENT (a numeric literal assigned directly to a variable)
"""

from __future__ import annotations

import re
import bisect
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

from src.violations.rules import get_rule 

@dataclass
class MagicNumberViolation:
    pr_id: int
    head_sha: str
    file_path: str
    line: int
    col: int
    literal: str
    context_type: str
    snippet: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "pr_id": self.pr_id,
            "head_sha": self.head_sha,
            "file_path": self.file_path,
            "line": self.line,
            "col": self.col,
            "literal": self.literal,
            "context_type": self.context_type,
            "snippet": self.snippet,
        }

# Detect numeric literals
NUM_LITERAL_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

# Detect known safe literals
SAFE_NAME_TOKENS = ("math.pi", "Math.PI", "MATH.PI")    # They are already named and standardized.
SAFE_LITERALS = {"0", "1"}

# Detect constant definition, skip entire line if it defines a constant
# 1) "const ...":
# JS/TS:    const PI = 3.14;
# Go:       const Pi = 3.14
# C#:       const double PI = 3.14;
# Rust:     const PI: f64 = 3.14;
# Kotlin:   const val PI = 3.14;
# Ruby:     PI = 3.14  (handled by PY_ALL_CAPS... instead)
CONST_DEF_RE = re.compile(
    r"""^\s*
        const
        (?:\s+val)?                 # Kotlin: const val
        (?:\s+[A-Za-z_][\w<>:\[\]]*)?  # optional (C#/Go/TS-ish)
        \s+[A-Za-z_$][\w$]*         # constant name
        (?:\s*:\s*[\w<>:\[\]]+)?    # Rust/TS type annotation after name
        \s*=\s*.+                   # assignment
    """,
    re.VERBOSE,
)

# 2) "final ...":
# Java:     final double PI = 3.14;
# Kotlin:   final val x = ...  (rare; Kotlin uses val, but "final" exists)
FINAL_DEF_RE = re.compile(
    r"""^\s*
        (?:public|private|protected)?\s*   # optional access modifier
        (?:static\s+)?                    # optional static
        final
        \s+[\w<>:\[\]]+                   # type token (double, int, List<T>, etc.)
        \s+[A-Za-z_$][\w$]*               # name
        \s*=\s*.+                         # assignment
    """,
    re.VERBOSE,
)

# 3) C/C++ preprocessor define:
# #define PI 3.14
CPP_DEF_RE = re.compile(
    r"""^\s*
        \#define
        \s+[A-Za-z_]\w*
        \s+.+                   # value
    """,
    re.VERBOSE,
)

# 4) C++ constexpr:
# constexpr int MAX_USERS = 100;
CONSTEXPR_DEF_RE = re.compile(
    r"""^\s*
        (?:inline\s+)?          # optional inline
        constexpr
        \s+[\w<>:\[\]]+         # type
        \s+[A-Za-z_]\w*         # name
        \s*=\s*.+               # assignment
    """,
    re.VERBOSE,
)

# 5) Python/Ruby convention:
# MAX_PASSWORD_LENGTH = 7
ALL_CAPS_CONST_DEF_RE = re.compile(r"^\s*[A-Z][A-Z0-9_]*\s*=\s*.+") 

# 6) PHP define("PI", 3.14);
PHP_DEFINE_CONST_DEF_RE = re.compile(
    r"^\s*define\s*\(\s*['\"][^'\"]+['\"]\s*,\s*.+\)\s*;?\s*$"
)

# 7) Swift let:
# let pi = 3.14
# let MAX_USERS: Int = 100
LET_DEF_RE = re.compile(
    r"""^\s*
        let
        \s+[A-Za-z_]\w*                 # name
        (?:\s*:\s*[\w<>\[\]:]+)?        # optional type annotation
        \s*=\s*.+                       # assignment
    """,
    re.VERBOSE,
)

# 8) Kotlin val:
# val pi = 3.14
# val MAX_USERS: Int = 100
VAL_DEF_RE = re.compile(
    r"""^\s*
        (?:private|public|protected|internal)?\s*   # optional visibility
        (?:lateinit\s+)?                           
        val
        \s+[A-Za-z_]\w*                            # name
        (?:\s*:\s*[\w<>\[\]:]+)?                   # optional type annotation
        \s*=\s*.+                                  # assignment
    """,
    re.VERBOSE,
)

CONST_DEF_PATTERNS = (
    CONST_DEF_RE,
    FINAL_DEF_RE,
    CPP_DEF_RE,
    CONSTEXPR_DEF_RE,
    ALL_CAPS_CONST_DEF_RE,
    PHP_DEFINE_CONST_DEF_RE,
    LET_DEF_RE,
    VAL_DEF_RE,
)

# Tokens can appear like "identifier(" but are NOT function calls.
# Exclude them to avoid misclassification:
#   if (x > 37)      as CALL_ARG (callee "if") -> Should be THRESHOLD
NON_CALL_KEYWORDS = {"if", "for", "while", "switch", "return", "catch"}


def detect_magic_numbers(code: Union[str, Sequence[str]], *, language: str = "generic") -> List[MagicNumberViolation]:
    """
    Detect magic numbers in a code.

    Args:
        Code: Code as a single string or list of lines

    Returns:
        List[MagicNumberViolation]
    """

    text = "\n".join(code) if not isinstance(code, str) else code

    lines, line_starts = _split_lines_with_starts(text)
    skip_line = _build_skip_line_flags(lines)

    violations: List[MagicNumberViolation] = []

    for m in NUM_LITERAL_RE.finditer(text):

        literal = m.group(0)

        if literal in SAFE_LITERALS:
            continue

        line_idx = _line_index_from_pos(line_starts, m.start())
        if line_idx < 0 or line_idx >= len(lines):
            continue

        if skip_line[line_idx]:
            continue

        line_text = lines[line_idx]
        col = (m.start() - line_starts[line_idx]) + 1

        context_type = _classify_context(
            line_text,
            m.start() - line_starts[line_idx],
            m.end() - line_starts[line_idx],
        )

        get_rule(context_type)

        violations.append(
            MagicNumberViolation(
                pr_id=0,
                head_sha="",
                file_path="<inline>",
                line=line_idx + 1,
                col=col,
                literal=literal,
                context_type=context_type,
                snippet=line_text,
            )
        )

    return violations


def _classify_context(line: str, lit_start: int, lit_end: int) -> str:
    """
    Context classifier:
    - LOOP_BOUND: inside range(...)
    - THRESHOLD: part of a comparison expression (> < >= <= == !=)
    - CALL_ARG: inside parentheses of a call-like expression
    - ASSIGNMENT: assigned directly to a variable
    - GENERIC: fallback
    """

    # 1) LOOP_BOUND: range( ... literal ... )
    range_pos = line.find("range(")
    if range_pos != -1:
        # If literal occurs after 'range(' and before next ')', treat as loop bound
        close = line.find(")", range_pos)
        if close != -1 and range_pos < lit_start < close:
            return "LOOP_BOUND"

    # 2) THRESHOLD: comparisons around literal
    # Check either: <op> literal  OR  literal <op>
    left = line[:lit_start]
    right = line[lit_end:]
    if re.search(r"(<=|>=|==|!=|<|>)\s*$", left) or re.search(r"^\s*(<=|>=|==|!=|<|>)", right):
        return "THRESHOLD"

    # 3) CALL_ARG: look for a call-like token name(...) where literal is inside (...)
    # Find the nearest '(' before the literal and see if it belongs to a non-keyword identifier.
    open_paren = line.rfind("(", 0, lit_start)
    close_paren = line.find(")", lit_end)
    if open_paren != -1 and close_paren != -1 and open_paren < lit_start < close_paren:
        # Grab the token before '('
        prefix = line[:open_paren]
        m = re.search(r"([A-Za-z_]\w*)\s*$", prefix)
        if m:
            callee = m.group(1)
            if callee not in NON_CALL_KEYWORDS:
                return "CALL_ARG"
    
    # 4) ASSIGNMENT: literal on right side of '=' (not comparison)
    eq_pos = line.find("=")

    if eq_pos != -1:
        if not re.search(r"(<=|>=|==|!=)", line):
            if eq_pos < lit_start:
                return "ASSIGNMENT"

    return "GENERIC"

# ============================================================
# HELPERS
# ============================================================

def _split_lines_with_starts(text: str):
    lines = text.splitlines()
    line_starts = []

    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line) + 1

    return lines, line_starts


def _build_skip_line_flags(lines: List[str]) -> List[bool]:
    skip = []

    for line in lines:

        stripped = line.strip()

        if not stripped:
            skip.append(True)
            continue

        if any(tok in line for tok in SAFE_NAME_TOKENS):
            skip.append(True)
            continue

        is_const_def = False
        for pat in CONST_DEF_PATTERNS:
            if pat.match(line):
                is_const_def = True
                break

        skip.append(is_const_def)

    return skip


def _line_index_from_pos(line_starts: List[int], pos: int) -> int:
    return bisect.bisect_right(line_starts, pos) - 1

