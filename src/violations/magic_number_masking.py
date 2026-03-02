"""
Magic Number Detector — Masking Layer
=====================================

Purpose
-------
This module implements the masking (sanitization) stage of the magic number
detector. Before scanning for numeric literals, the source code is first
sanitized to prevent false positives.

Masking replaces specific spans of text with whitespace (rather than deleting
them).

What Gets Masked
----------------

1) String literals
   - Single-quoted strings ('...')
   - Double-quoted strings ("...")
   - JavaScript template strings (`...`)
   - Python triple-quoted strings ('''...''')

2) Comments
   - Single-line comments (//, #)
   - Block comments (/* ... */), including multi-line blocks

3) JavaScript / TypeScript regex literals
   - Patterns such as /\\d{3}/g

Why Mask Instead of Remove?
---------------------------
Masked content is replaced with spaces of equal length. This preserves
character positions so that line and column numbers reported by the
detector correspond to the original source file.
"""

from __future__ import annotations

import re
from typing import Optional, Pattern, Tuple

# String literals
RX_SINGLE_QUOTED_STRING = r"'[^'\\]*(?:\\.[^'\\]*)*'"
RX_DOUBLE_QUOTED_STRING = r'"[^"\\]*(?:\\.[^"\\]*)*"'
RX_TEMPLATE_STRING_SINGLE_LINE = r"`[^`\\]*(?:\\.[^`\\]*)*`"

# Python triple quoted strings 
RX_TRIPLE_SINGLE_QUOTED_OPEN = r"'''"
RX_TRIPLE_DOUBLE_QUOTED_OPEN = r'"""'

# Combined single line string pattern
RX_ANY_SINGLE_LINE_STRING = rf"(?:{RX_SINGLE_QUOTED_STRING}|{RX_DOUBLE_QUOTED_STRING}|{RX_TEMPLATE_STRING_SINGLE_LINE})"
STRING_RE: Pattern[str] = re.compile(RX_ANY_SINGLE_LINE_STRING, re.VERBOSE)

# Comments
RX_LINE_COMMENT = r"//.*$"
RX_HASH_COMMENT = r"#.*$"
LINE_COMMENT_RE: Pattern[str] = re.compile(RX_LINE_COMMENT)
HASH_COMMENT_RE: Pattern[str] = re.compile(RX_HASH_COMMENT)

# Single line block comment /* ... */
RX_BLOCK_COMMENT_SINGLE_LINE = r"/\*.*?\*/"
BLOCK_COMMENT_RE: Pattern[str] = re.compile(RX_BLOCK_COMMENT_SINGLE_LINE)

# Regex literals: /pattern/flags 
RX_REGEX_LITERAL = r"""
/                      # opening slash
(?:[^/\\]|\\.)+        # non-slash or escaped characters
/[gimsuy]*             # closing slash + optional flags
"""
REGEX_LITERAL_RE: Pattern[str] = re.compile(RX_REGEX_LITERAL, re.VERBOSE)


def mask_with_spaces(line: str, rx: Pattern[str]) -> str:
    """
    Replace matched spans with spaces to preserve column indices.
    """
    def repl(m: re.Match) -> str:
        return " " * (m.end() - m.start())
    return rx.sub(repl, line)


def starts_or_ends_triple_quote(line: str) -> Optional[str]:
    """
    Return which triple quote delimiter is seen on this line, if any:
    - \"\"\" or '''
    We treat this as a toggle if the delimiter count is odd.
    """
    count_dq = line.count('"""')
    count_sq = line.count("'''")
    if count_dq % 2 == 1:
        return '"""'
    if count_sq % 2 == 1:
        return "'''"
    return None


def sanitize_line(
    line: str,
    *,
    lang: str,
    in_py_triple_string: bool,
    triple_delim: str,
    in_c_block_comment: bool,
) -> Tuple[str, bool, str, bool]:
    """
    Sanitize a line for numeric scanning

    For JS/TS/Java:
      - mask strings
      - mask comments (//, /*...*/, #)
      - handle multi-line /* ... */ 
      - mask regex literals /.../ 

    For Python:
      - mask single-line strings
      - mask # comments
      - handle triple-quoted strings with simple state toggle

    Returns: (sanitized_line, new_in_triple, new_delim, new_in_c_block_comment)
    """
    # Python handling
    if lang == "python":
        toggle = starts_or_ends_triple_quote(line)

        # If currently inside a triple quoted string
        if in_py_triple_string:
            masked = " " * len(line)
            if toggle == triple_delim:
                # Close the triple string on this line
                return masked, False, "", in_c_block_comment
            return masked, True, triple_delim, in_c_block_comment

        # Check if this line starts a triple quoted string
        if toggle is not None:
            # Start triple string; mask the entire line for safety
            return (" " * len(line)), True, toggle, in_c_block_comment

        # Mask strings and # comments
        out = mask_with_spaces(line, STRING_RE)
        out = mask_with_spaces(out, HASH_COMMENT_RE)
        return out, False, "", in_c_block_comment

    # Multi-line C-style block comments: /* ... */
    # Example:
    #   /*
    #    * @requires jQuery 1.2.6
    #    */
    if in_c_block_comment:
        masked = " " * len(line)
        if "*/" in line:
            # Block comment ends on this line
            return masked, in_py_triple_string, triple_delim, False
        return masked, in_py_triple_string, triple_delim, True

    # Detect start of multi line block comment
    start_idx = line.find("/*")
    if start_idx != -1:
        end_idx = line.find("*/", start_idx + 2)
        if end_idx == -1:
            # Block comment starts and continues to next lines
            masked = " " * len(line)
            return masked, in_py_triple_string, triple_delim, True
        # else: single line block comment, handled below

    # Mask strings and comments
    out = mask_with_spaces(line, STRING_RE)
    out = mask_with_spaces(out, BLOCK_COMMENT_RE)  # single-line /* ... */
    out = mask_with_spaces(out, LINE_COMMENT_RE)
    out = mask_with_spaces(out, HASH_COMMENT_RE)

    # Only JS/TS has /.../ regex literal syntax
    if lang in {"javascript", "typescript"}:
        out = mask_with_spaces(out, REGEX_LITERAL_RE)

    return out, False, "", in_c_block_comment