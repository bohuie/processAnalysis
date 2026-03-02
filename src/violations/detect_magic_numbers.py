"""
Magic Number Detector
=====================

Definition
----------
A magic number is a numeric literal embedded directly in source code
without an explanatory constant name, especially when used within
meaningful program logic.

Scope
-----
This detector analyzes the following languages:

    - JavaScript (.js, .jsx)
    - TypeScript (.ts, .tsx)
    - Python (.py)
    - Java (.java)

It identifies numeric literals that appear in logical program contexts,
including:

    • Function or method arguments      → retry(5)
    • Conditional thresholds            → if (count > 7)
    • Loop bounds                       → for (i < 10)
    • Direct variable assignments       → timeout = 30

What Is Ignored
--------------------------

1) Literal constant definitions:
    - JS/TS:   const MAX = 5;
    - Python:  MAX_RETRY = 5
    - Java:    static final int MAX = 5;

   Only literal RHS values are skipped.
   Expressions such as `const X = getLimit(5)` are still analyzed.

2) Formatting / presentation numbers:
    - JSX style or sx props
    - UI layout props (width, height, margin, etc.)
    - CSS declarations (margin: 12px;)
    - Values with CSS units (12px, 2rem, 50%)
    - Styling/theme blocks (createTheme, makeStyles)
    - Python UI attribute dictionaries ({"rows": 5})

3) Strings and comments:
    - Single/double/template strings
    - Python triple-quoted strings
    - Line comments (//, #)
    - Block comments (/* ... */)
    - JS regex literals (/pattern/)

4) Non-project or generated code:
    - node_modules, site-packages, dist, build, vendor, etc.
    - Minified files

5) Safe literals:
    - 0 and 1 are not flagged by default.

Methodological Notes
--------------------
This detector use heuristic approach (regex + contextual rules).
The goal is to identify magic numbers in logical contexts while
minimizing false positives from formatting or presentation code.

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Union

from src.violations.magic_number_config import (
    ALLOWED_LANGS,
    RULES,
    SAFE_LITERALS,
    PRESENTATION_PROP_NAMES,
)
from src.violations.magic_number_literals import NUMERIC_RE, is_literal_only_rhs
from src.violations.magic_number_masking import sanitize_line
from src.violations.magic_number_filters import (
    JSX_PRESENTATION_ATTR_RE,
    STYLE_CALL_OPEN_RE,
    is_allowed_file,
    is_css_like_declaration_line,
    is_python_ui_attr_dict_line,
    line_has_css_unit_after_number,
    line_has_presentation_prop_assign,
    normalize_language,
    update_depth,
)
from src.violations.magic_number_classify import classify_context


# ============================================================
# Data model
# ============================================================

@dataclass(frozen=True)
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


# ============================================================
# Constant definition detection
# ============================================================

import re
from typing import Optional, Tuple

# JS/TS: const NAME = <rhs>
RX_JS_CONST_DEF = r"^\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*(.+?);?\s*$"
JS_CONST_RE = re.compile(RX_JS_CONST_DEF)

# Python: UPPER_SNAKE_CASE = <rhs>
RX_PY_CONST_DEF = r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$"
PY_CONST_RE = re.compile(RX_PY_CONST_DEF)

# Java: (public/protected/private)? static final TYPE NAME = <rhs>;
RX_JAVA_CONST_DEF = (
    r"^\s*"
    r"(?:(?:public|protected|private)\s+)?"
    r"(?:static\s+final|final\s+static)\s+"
    r"(?:[\w$<>\[\], ?]+)\s+"          
    r"([A-Z_][A-Z0-9_]*)\s*=\s*"       
    r"(.+?)\s*;\s*$"                  
)
JAVA_CONST_RE = re.compile(RX_JAVA_CONST_DEF)


def _extract_const_rhs(lang: str, line_sanitized: str) -> Optional[Tuple[str, str]]:
    """
    Extract (NAME, RHS) from constant definition lines.

    Returns None if not a constant definition.
    """
    if lang in {"javascript", "typescript"}:
        m = JS_CONST_RE.match(line_sanitized)
        if not m:
            return None
        return m.group(1), m.group(2).strip()

    if lang == "python":
        m = PY_CONST_RE.match(line_sanitized)
        if not m:
            return None
        return m.group(1), m.group(2).strip()

    if lang == "java":
        m = JAVA_CONST_RE.match(line_sanitized)
        if not m:
            return None
        return m.group(1), m.group(2).strip()

    return None


# ============================================================
# Main detection function
# ============================================================

def detect_magic_numbers(
    code: Union[str, Sequence[str]],
    *,
    language: str = "generic",
    file_path: str = "<inline>",
    pr_id: int = 0,
    head_sha: str = "",
) -> List[MagicNumberViolation]:
    """
    Heuristic magic number detector.

    Scope:
      - Scans JavaScript, TypeScript, Python, Java files
      - Returns empty list for other languages/non-matching paths

    What we ignore:
      - Strings and comments 
      - JS/TS regex literals /.../ 
      - Multi-line block comments /* ... */ 
      - CSS declarations with units (margin: 12px;)
      - JSX presentation props (style/sx/viewBox/width/height/etc.)
      - Styling function blocks (createTheme/makeStyles)
      - Python UI attribute dicts ({"rows": 5, "cols": 23})
      - CLI/config command strings ("-blur 0x8 -resize ...")

    Constant handling:
      - JS/TS: skips "const NAME = <literal>" (literal-only RHS)
      - Python: skips "UPPER_SNAKE = <literal>" (literal-only RHS)
      - Java: skips "(access)? (static final|final static) TYPE NAME = <literal>;" (literal-only RHS)
      - Does NOT skip expressions like:
          const MAX = getLimit(5);          <- still scanned
          LIMIT = calculate(10);            <- still scanned
          static final int X = get(5);      <- still scanned

    Python:
      - Handles triple quoted strings with simple on/off toggle
      - Masks entire line while inside triple quoted region
    """
    # Determine language
    lang = normalize_language(language, file_path)

    # Early exit if language not supported
    if lang not in ALLOWED_LANGS:
        return []

    # Convert to string if needed
    source = "\n".join(code) if not isinstance(code, str) else code

    # Filter out excluded/minified files
    if file_path != "<inline>" and not is_allowed_file(file_path, source):
        return []

    lines = source.splitlines()
    violations: List[MagicNumberViolation] = []

    # State tracking for JS/TS ignore regions
    in_style_call: bool = False
    style_paren_depth: int = 0
    style_brace_depth: int = 0

    in_jsx_presentation_obj: bool = False
    jsx_brace_depth: int = 0

    # State tracking for Python triple quoted strings
    in_py_triple_string: bool = False
    py_triple_delim: str = ""

    # State tracking for C style block comments
    in_c_block_comment: bool = False

    # Process each line
    for i, original_line in enumerate(lines, start=1):
        line_sanitized, in_py_triple_string, py_triple_delim, in_c_block_comment = sanitize_line(
            original_line,
            lang=lang,
            in_py_triple_string=in_py_triple_string,
            triple_delim=py_triple_delim,
            in_c_block_comment=in_c_block_comment,
        )


        # Skip CSS formatting lines
        if is_css_like_declaration_line(line_sanitized):
            continue

        # Python: skip UI attribute dicts
        if lang == "python":
            if is_python_ui_attr_dict_line(original_line):
                continue

        # JS/TS: skip lines with presentation prop assignments
        if lang in {"javascript", "typescript"}:
            if line_has_presentation_prop_assign(line_sanitized):
                continue

        # JS/TS: Track multi line JSX presentation object regions
        # Example: style={{ ... }} spanning multiple lines
        if lang in {"javascript", "typescript"}:
            if not in_jsx_presentation_obj:
                m_attr = JSX_PRESENTATION_ATTR_RE.search(line_sanitized)
                if m_attr and m_attr.group(1) in PRESENTATION_PROP_NAMES:
                    in_jsx_presentation_obj = True
                    jsx_brace_depth = 0

            if in_jsx_presentation_obj:
                jsx_brace_depth = update_depth(line_sanitized, jsx_brace_depth, "{", "}")
                if jsx_brace_depth <= 0 and "}" in original_line:
                    in_jsx_presentation_obj = False
                continue  # Skip this line

        # JS/TS: Track createTheme/makeStyles ignore regions
        if lang in {"javascript", "typescript"}:
            if not in_style_call and STYLE_CALL_OPEN_RE.search(line_sanitized):
                in_style_call = True
                style_paren_depth = 0
                style_brace_depth = 0

            if in_style_call:
                style_paren_depth = update_depth(line_sanitized, style_paren_depth, "(", ")")
                style_brace_depth = update_depth(line_sanitized, style_brace_depth, "{", "}")

                if style_paren_depth <= 0 and style_brace_depth <= 0 and ")" in line_sanitized:
                    in_style_call = False

                if in_style_call:
                    continue  # Skip this line

        # Skip constant definitions with literal only RHS
        const_info = _extract_const_rhs(lang, line_sanitized)
        if const_info is not None:
            _, rhs = const_info
            if is_literal_only_rhs(rhs):
                continue  # Skip this constant definition

        # Detect numeric literals on this line
        for m in NUMERIC_RE.finditer(line_sanitized):
            lit = m.group(0)

            # Skip safe literals (0 and 1)
            if lit in SAFE_LITERALS:
                continue

            # Skip numbers with CSS units (formatting)
            if line_has_css_unit_after_number(line_sanitized, m.end()):
                continue

            # Classify the context
            context_type = classify_context(lang, line_sanitized, (m.start(), m.end()))
            if context_type not in RULES:
                context_type = "GENERIC"

            # Create violation record
            violations.append(
                MagicNumberViolation(
                    pr_id=pr_id,
                    head_sha=head_sha,
                    file_path=file_path,
                    line=i,
                    col=m.start() + 1,  # Convert to 1-based column
                    literal=lit,
                    context_type=context_type,
                    snippet=original_line,
                )
            )

    return violations