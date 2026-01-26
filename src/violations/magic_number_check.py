"""
MagicNumberCheck (v1) — simple, testable detector based on lightweight parsing.

Goal:
- Implement core detection logic on synthetic code snippets
- Support controlled unit tests (no repo I/O here)
- Keep behavior configurable and easy to extend later (AST, multi-language, etc.)

This module intentionally starts with a *heuristic* approach:
- Find numeric literals in code lines
- Ignore allowed numbers (e.g., 0, 1)
- Ignore literals in constant declarations (e.g., static final)
- Ignore literals in annotations (e.g., @Something(123)) if configured
- Flag the rest as "magic numbers"

Later versions can replace the parsing with language-specific AST tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Set, Tuple
import re

# Data structures

@dataclass(frozen=True)
class MagicNumberFinding:
    """Represents one detected magic number occurrence."""
    literal: str                 # e.g. "24", "1.05", "1000"
    line_no: int                 # 1-based line number
    column: int                  # 0-based column index (best-effort)
    line_text: str               # the full source line (for debugging/tests)
    reason: str = "numeric literal used directly in code"


@dataclass
class MagicNumberConfig:
    """
    Configuration for MagicNumberCheck.

    Notes:
    - ignored_numbers: numbers that are allowed as literals (commonly {0, 1}).
      Can extend later (e.g., JetBrains ignores many small ints by default).
    - ignore_in_constant_declarations: ignore numeric literals on constant definition lines
      (e.g., 'static final int X = 24;'). Tools differ on border cases.
    - ignore_in_annotations: ignore numeric literals in annotation lines (e.g., '@Size(10)').
    - treat_negative_as_literal: if True, "-1" is treated as a single literal; else "1" with unary '-'.
    """
    ignored_numbers: Set[str] = field(default_factory=lambda: {"0", "1"})
    ignore_in_constant_declarations: bool = True
    ignore_in_annotations: bool = True
    treat_negative_as_literal: bool = True

    # Optional future config knobs
    ignore_in_hashcode_method: bool = False  # placeholder for later

# Public API

def detect_magic_numbers_from_code(code: str, config: Optional[MagicNumberConfig] = None) -> List[MagicNumberFinding]:
    """
    Detect magic numbers from a code snippet (string).

    This function is designed for unit tests and synthetic examples.
    It does not perform language-aware parsing; it uses robust heuristics.

    Args:
        code: Source code as a string (can be Java/Python/etc. for heuristics).
        config: Optional MagicNumberConfig.

    Returns:
        List of MagicNumberFinding.
    """
    cfg = config or MagicNumberConfig()
    findings: List[MagicNumberFinding] = []

    for idx, line in enumerate(code.splitlines(), start=1):
        stripped = line.strip()

        # Skip empty lines quickly
        if not stripped:
            continue

        # Optional: ignore annotation lines (Java-like)
        if cfg.ignore_in_annotations and _is_annotation_line(stripped):
            continue

        # Optional: ignore constant declarations (Java-like)
        if cfg.ignore_in_constant_declarations and _is_constant_declaration_line(stripped):
            # NOTE: Border cases like "final int HOURS = 20 + 4;" are subjective.
            continue

        # Extract numeric literals from the line
        literals = _extract_numeric_literals(line, treat_negative_as_literal=cfg.treat_negative_as_literal)

        for literal, col in literals:
            normalized = _normalize_literal(literal)

            # Ignore configured allowed values
            if normalized in cfg.ignored_numbers:
                continue

            # Ignore numeric tokens that are part of an identifier
            # e.g., var1 or HTTP2. This is a rough check; can be improved later.
            if _looks_like_identifier_embedded_number(line, col, literal):
                continue

            findings.append(
                MagicNumberFinding(
                    literal=literal,
                    line_no=idx,
                    column=col,
                    line_text=line.rstrip("\n"),
                    reason="numeric literal used directly outside named constant",
                )
            )

    return findings


def count_magic_numbers_from_code(code: str, config: Optional[MagicNumberConfig] = None) -> int:
    """Convenience wrapper to return count only."""
    return len(detect_magic_numbers_from_code(code, config=config))


# Internal helpers (heuristics)

# Regex for numeric literals:
# - integers: 123, 0
# - floats: 1.05, .5, 5.
# - scientific: 1e10, 1.2E-3
# Notes: can be extended later.
_NUMERIC_LITERAL_RE = re.compile(
    r"""
    (?P<num>
        (?:\d+\.\d*|\.\d+|\d+)        # int or float
        (?:[eE][+-]?\d+)?             # optional exponent
    )
    """,
    re.VERBOSE,
)

# Negative numeric literal handling:
# Treat "-123" as a literal only when '-' appears as unary minus,
# which is hard without parsing. For now, merge "-" with number
# if immediately adjacent: "-42", "-1.0", "-.5"
_NEGATIVE_NUMERIC_LITERAL_RE = re.compile(
    r"""
    (?P<num>
        -
        (?:\d+\.\d*|\.\d+|\d+)
        (?:[eE][+-]?\d+)? 
    )
    """,
    re.VERBOSE,
)


def _extract_numeric_literals(line: str, treat_negative_as_literal: bool) -> List[Tuple[str, int]]:
    """
    Return list of (literal, column) occurrences for numeric literals in the line.
    Column is 0-based and best-effort.

    If treat_negative_as_literal is True, match negatives like "-1".
    """
    literals: List[Tuple[str, int]] = []

    # 1) Extract negative literals first (to avoid capturing the "1" part separately)
    consumed_spans: List[Tuple[int, int]] = []
    if treat_negative_as_literal:
        for m in _NEGATIVE_NUMERIC_LITERAL_RE.finditer(line):
            lit = m.group("num")
            start = m.start("num")
            end = m.end("num")
            literals.append((lit, start))
            consumed_spans.append((start, end))

    def _span_consumed(pos: int) -> bool:
        for s, e in consumed_spans:
            if s <= pos < e:
                return True
        return False

    # 2) Extract non-negative literals, skipping overlaps with negative matches
    for m in _NUMERIC_LITERAL_RE.finditer(line):
        lit = m.group("num")
        start = m.start("num")
        if _span_consumed(start):
            continue
        literals.append((lit, start))

    return literals


def _normalize_literal(literal: str) -> str:
    """
    Normalize literal string to compare with ignored_numbers.
    For now keep it simple: strip underscores and whitespace.
    """
    return literal.strip().replace("_", "")


def _is_annotation_line(stripped_line: str) -> bool:
    """Java-like heuristic: lines starting with '@' are annotations."""
    return stripped_line.startswith("@")


def _is_constant_declaration_line(stripped_line: str) -> bool:
    """
    Heuristic for constant declarations (Java-like):
    - contains 'final' AND '=' on the same line
    - common forms: 'static final int X = 24;' or 'final double TAX = 0.05;'
    """
    # Basic heuristic:
    if "final" not in stripped_line:
        return False
    if "=" not in stripped_line:
        return False

    # Exclude cases that are obviously not declarations (very rough)
    # e.g., 'finally' keyword in try/catch
    if "finally" in stripped_line:
        return False

    return True


def _looks_like_identifier_embedded_number(line: str, col: int, literal: str) -> bool:
    """
    Best-effort check: if the character immediately before/after the literal is
    an identifier char (letter, digit, underscore), then it might be part of a name.
    E.g., var1, HTTP2, x100.

    This is not perfect, but prevents common false positives.
    """
    start = col
    end = col + len(literal)

    def is_ident_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    if start - 1 >= 0 and is_ident_char(line[start - 1]):
        return True
    if end < len(line) and is_ident_char(line[end]):
        return True
    return False

def extract_code_from_patch_snippet(patch_snippet: str) -> str:
    """
    Convert a git diff 'patch snippet' into plain code lines.

    Intentionally drop diff metadata lines like:
      - @@ -a,b +c,d @@
      - diff --git, index, ---/+++
    And strip the leading diff prefix ("+", "-", " ") from code lines.

    This makes Team-scale testing possible using file_changes.csv.patch_snippet,
    without fetching full repo files.
    """
    out_lines: List[str] = []

    for raw in patch_snippet.splitlines():
        line = raw.rstrip("\n")

        # Skip diff metadata / headers
        if line.startswith("@@"):
            continue
        if line.startswith("diff --git"):
            continue
        if line.startswith("index "):
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue

        # Skip "\ No newline at end of file" marker
        if line.startswith("\\ No newline"):
            continue

        # Strip leading diff markers for actual code lines
        if line.startswith(("+", "-", " ")):
            out_lines.append(line[1:])
        else:
            # If it's an unexpected line format, keep it as-is (best effort)
            out_lines.append(line)

    return "\n".join(out_lines)

