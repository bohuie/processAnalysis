"""
Magic Number Detector — Filtering and Scope Control
====================================================

Purpose
-------
This module defines the filtering rules that determine:

    • Which files should be analyzed
    • Which languages are supported
    • Which numeric contexts should be excluded

The detection focuses on meaningful program logic rather than
formatting, generated code, or external libraries.

File Filtering
--------------------
The detector only processes supported source files:

    - JavaScript (.js, .jsx)
    - TypeScript (.ts, .tsx)
    - Python (.py)
    - Java (.java)

Files are excluded if they:

    • Reside in vendor or dependency directories
      (e.g., node_modules, site-packages, build, dist)
    • Appear to be minified
    • Do not match allowed extensions

Formatting and Presentation Exclusions
---------------------------------------
To reduce false positives, the detector ignores numbers that are 
used for styling or layout purposes, including:

    • CSS property declarations (e.g., margin: 12px;)
    • Values followed by CSS units (px, rem, %, etc.)
    • JSX presentation props (width, height, margin, spacing, etc.)
    • Styling/theme function blocks (createTheme, makeStyles)
    • Python UI attribute dictionaries (e.g., {"rows": 5})

These numbers are considered formatting constants, which is out of the scope of magic number detector.
"""

from __future__ import annotations

import re
from typing import Tuple

from src.violations.magic_number_config import (
    ALLOWED_EXTS,
    CSS_UNITS,
    EXCLUDED_PATH_KEYWORDS,
    MAX_MINIFIED_LINE_RATIO,
    MAX_REASONABLE_LINE_LENGTH,
    PRESENTATION_CALL_NAMES,
    PRESENTATION_PROP_NAMES,
    PY_PRESENTATION_KEYWORDS,
)

def guess_language_from_path(file_path: str) -> str:
    """Guess programming language from file extension."""
    p = file_path.lower()

    if p.endswith((".js", ".jsx")):
        return "javascript"
    if p.endswith((".ts", ".tsx")):
        return "typescript"
    if p.endswith(".py"):
        return "python"
    if p.endswith(".java"):
        return "java"

    return "generic"


def normalize_language(language: str, file_path: str) -> str:
    """
    Normalize language string and use file path as fallback.
    """
    lang = (language or "").lower().strip()

    if not lang or lang == "generic":
        lang = guess_language_from_path(file_path)

    # Special case: TypeScript files mislabeled as JavaScript
    if lang == "javascript" and file_path.lower().endswith((".ts", ".tsx")):
        lang = "typescript"

    return lang


def is_excluded_path(file_path: str) -> bool:
    """Check if file path contains excluded keywords."""
    lower = file_path.lower()
    return any(keyword in lower for keyword in EXCLUDED_PATH_KEYWORDS)


def is_minified_file(file_path: str, source: str) -> bool:
    """
    Heuristic check for minified files.

    Indicators:
      - .min.js extension
      - Very few lines but large file size
      - Many extremely long lines
    """
    lower = file_path.lower()

    # Explicit minified file extension
    if lower.endswith(".min.js"):
        return True

    lines = source.splitlines()

    # Very few lines but huge file → probably minified
    if len(lines) <= 5 and len(source) > 2000:
        return True

    # Check for ratio of extremely long lines
    if lines:
        long_lines = sum(1 for l in lines if len(l) > MAX_REASONABLE_LINE_LENGTH)
        if (long_lines / len(lines)) > MAX_MINIFIED_LINE_RATIO:
            return True

    return False


def is_allowed_file(file_path: str, source: str) -> bool:
    """
    Determine if we should process this file.

    Checks:
      - Has allowed extension
      - Not in excluded path
      - Not minified
    """
    lower = file_path.lower()

    # Must have allowed extension
    if not lower.endswith(ALLOWED_EXTS):
        return False

    # Skip excluded paths
    if is_excluded_path(lower):
        return False

    # Skip minified files
    if is_minified_file(lower, source):
        return False

    return True

# Pattern to detect styling function calls like createTheme(...)
RX_STYLE_CALL_OPEN = r"\b(" + "|".join(re.escape(n) for n in sorted(PRESENTATION_CALL_NAMES)) + r")\s*\("
STYLE_CALL_OPEN_RE = re.compile(RX_STYLE_CALL_OPEN)

# JSX presentation attribute opening: style={{ ... }}, sx={{ ... }}
RX_JSX_PRESENTATION_ATTR_OPEN = r"\b([A-Za-z_][\w]*)\s*=\s*\{\s*\{"
JSX_PRESENTATION_ATTR_RE = re.compile(RX_JSX_PRESENTATION_ATTR_OPEN)

# JSX prop assignment pattern: <Box width={12} />
RX_JSX_PROP_ASSIGN = r"\b([A-Za-z_][\w]*)\s*=\s*\{"
JSX_PROP_ASSIGN_RE = re.compile(RX_JSX_PROP_ASSIGN)


def update_depth(text: str, depth: int, open_ch: str, close_ch: str) -> int:
    """
    Update bracket/paren depth counter.
    Used to track nesting level in styling blocks.
    """
    return depth + text.count(open_ch) - text.count(close_ch)


def line_has_css_unit_after_number(line_sanitized: str, num_end_idx: int) -> bool:
    """
    Check if a number is immediately followed by a CSS unit.
    Examples: 12px, 2rem, 50%
    """
    tail = line_sanitized[num_end_idx: num_end_idx + 8].lstrip()
    return any(tail.startswith(u) for u in CSS_UNITS)


def is_css_like_declaration_line(line_sanitized: str) -> bool:
    """
    Detect CSS property declarations.
    Examples:
      margin: 12px;
      padding: 8px;
    """
    has_colon_structure = bool(re.match(r"^\s*[-a-zA-Z]+\s*:\s*.*$", line_sanitized))
    has_css_unit = any(u in line_sanitized for u in CSS_UNITS)
    return has_colon_structure and has_css_unit


def line_looks_like_jsx(line: str) -> bool:
    """
    Quick heuristic check for JSX syntax.
    Looks for '<' and either '/>' or '>'.
    """
    return ("<" in line) and ("/>" in line or ">" in line)


def line_has_presentation_prop_assign(line_sanitized: str) -> bool:
    """
    Check if line contains JSX presentation prop assignments.
    Examples:
      <Box width={12} height={24} />
      <Stack spacing={2} />
      <Typography fontSize={14} />
    """
    if not line_looks_like_jsx(line_sanitized):
        return False

    for m in JSX_PROP_ASSIGN_RE.finditer(line_sanitized):
        prop = m.group(1)
        if prop in PRESENTATION_PROP_NAMES:
            return True

    return False


def is_python_ui_attr_dict_line(original_line: str) -> bool:
    """
    Detect Python UI attribute dictionaries.
    Example: attrs={"rows": 5, "cols": 23}
    """
    low = original_line.lower()

    if "attrs" not in low:
        return False

    return any(
        (f'"{k}"' in original_line) or (f"'{k}'" in original_line)
        for k in PY_PRESENTATION_KEYWORDS
    )
