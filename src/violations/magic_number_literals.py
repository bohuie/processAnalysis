"""
Magic Number Detector — Numeric Literal Definitions
===================================================

Purpose
-------
This module defines the regular expressions used to identify numeric
literals within source code. It is responsible for detecting standalone
decimal numbers that may represent potential magic numbers in program logic.

Scope of Detection
------------------
The detector intentionally focuses only on simple decimal literals:

    • Integers: 123
    • Negative integers: -10
    • Floats: 1.23, 1., .25

The following numeric forms are excluded:

    • Hexadecimal literals (0xFF)
    • Binary literals (0b1010)
    • Scientific notation (1e10, 3.5e-4)
    • Underscore separated numbers (1_000)
    • Java numeric suffixes (10L, 0.5f, 2D)

These exclusions reflect the design goal of identifying application level
logical constants (e.g., thresholds, limits, loop bounds).

Design Considerations
---------------------
- Word-boundary assertions prevent matching numbers embedded inside identifiers
  (e.g., `version1`, `abc123def`).
- An optional leading minus allows detection of negative constants.
- Literal only checks are used to skip constant definitions where the right-hand
  side is purely a numeric literal.
"""

from __future__ import annotations

import re
from typing import Pattern

# Ensure the character before the number must nit be a letter, digit, underscore, dollar sign
RX_LEFT_WORD_BOUNDARY = r"(?<![\w$])"   
RX_RIGHT_WORD_BOUNDARY = r"(?![\w$])"  

# Support negative numbers like -10
RX_OPTIONAL_MINUS = r"-?"              #

# Float forms: 1.23, 1., .25
RX_FLOAT_MANTISSA = r"(?:\d+\.\d+|\d+\.|\.\d+)"
RX_FLOAT_LITERAL = RX_FLOAT_MANTISSA

# Integer forms: 123
RX_INT_MANTISSA = r"\d+"
RX_INT_LITERAL = RX_INT_MANTISSA

# Combined numeric literal pattern
RX_NUMERIC_LITERAL = rf"""
{RX_LEFT_WORD_BOUNDARY}
{RX_OPTIONAL_MINUS}
(?:
    {RX_FLOAT_LITERAL}
    |
    {RX_INT_LITERAL}
)
{RX_RIGHT_WORD_BOUNDARY}
"""

NUMERIC_RE: Pattern[str] = re.compile(RX_NUMERIC_LITERAL, re.VERBOSE)

# Literal only RHS check 
RX_LITERAL_ONLY = rf"""^\s*{RX_OPTIONAL_MINUS}(?:{RX_FLOAT_LITERAL}|{RX_INT_LITERAL})\s*$"""
LITERAL_ONLY_RE: Pattern[str] = re.compile(RX_LITERAL_ONLY, re.VERBOSE)


def is_literal_only_rhs(rhs: str) -> bool:
    """
    Check if RHS is exactly a numeric literal (not a call or expression).

    Examples (True):
      "123"
      "-10"
      "0.5"
      ".25"
      "1."

    Examples (False):
      "1_000"
      "1e10"
      "0xFF"
      "0b1010"
      "10L"
      "getLimit(5)"
      "MAX_VALUE + 1"
    """
    return LITERAL_ONLY_RE.match(rhs) is not None