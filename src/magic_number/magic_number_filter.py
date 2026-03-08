"""
Magic Number Filtering Utilities

This module provides the preprocessing and filtering utilities used by the
magic number detector pipeline.

Summary:

1. File filtering
   - Skip non-relevant files such as formatting files, vendor libraries,
     generated artifacts, test folders, and styling directories.

2. Code cleaning
   - Remove block comments, regex literals, strings, and single-line comments
     before numeric detection.

3. Stateful parsing
   - Maintain scanning state for block comments, strings, and presentation
     styling blocks across lines.

4. Context detection
   - Identify constant definitions and non-logic content (HTML/SVG).

5. Numeric filtering helpers
   - Provide context checks used after numeric detection to skip numbers that
     belong to styling, HTTP status codes, object keys, RGB colors, or other
     presentation contexts.

These utilities are called by the main detector to focus the analysis on numbers used in program logic.
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, Any

from .magic_number_patterns import (
    FORMAT_EXTENSIONS,
    STYLE_FOLDERS,
    EXCLUDED_PATH_KEYWORDS,
    HASH_COMMENT_LANGS,
    CSS_UNITS,
    STYLE_KEYWORDS,
    PRESENTATION_CALL_NAMES,
    PRESENTATION_KEYWORDS,
    LOOKBACK_WINDOW,
    CONST_DEF_PATTERNS_BY_LANG,
    PRESENTATION_BLOCK_OPENERS,
    HTTP_STATUS_CODES,
)

# ----------------------------
# (0) File Filtering
# ----------------------------

def should_skip_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in FORMAT_EXTENSIONS:
        return True

    normalized = file_path.replace("\\", "/").lower()

    # Check for minified files
    if normalized.endswith(".min.js") or normalized.endswith(".min.css") or "-min." in normalized:
        return True

    # Skip files that contain third-party code, generated artifacts, or non-logical content
    for kw in EXCLUDED_PATH_KEYWORDS:
        if kw in normalized:
            return True

    # Skip style/theming folders
    for folder in STYLE_FOLDERS:
        if folder in normalized:
            return True

    return False


@dataclass
class CommentState:
    in_block_comment: bool = False


@dataclass
class StringState:
    in_string: bool = False
    mode: str = "NONE"  # SINGLE, DOUBLE, BACKTICK, PY_TRIPLE_SINGLE, PY_TRIPLE_DOUBLE, CSHARP_VERBATIM, NONE


@dataclass
class StyleBlockState:
    in_style_block: bool = False
    brace_depth: int = 0


# ------------------------------------
# (1) Remove block comments /* ... */
# ------------------------------------

def remove_block_comments(line: str, state: CommentState) -> str:
    """
    Removes block comments /* ... */ across lines using state.
    Keeps the remaining code on the line (deletes comment content).
    """
    out = ""
    i = 0

    while i < len(line):
        if state.in_block_comment:
            end = line.find("*/", i)
            if end == -1:
                return out  # Whole remainder is comment
            i = end + 2
            state.in_block_comment = False
            continue

        start = line.find("/*", i)
        if start == -1:
            out += line[i:]
            break

        out += line[i:start]
        state.in_block_comment = True
        i = start + 2

    return out


# ------------------------------------
# (2) Remove regex literals
# ------------------------------------

def remove_regex_literals(line: str, language: str) -> str:
    if language not in {"javascript", "typescript", "php"}:        
        return line

    result = []
    i = 0
    n = len(line)

    while i < n:

        # Do not treat // as regex
        if line[i] == "/" and i + 1 < n and line[i + 1] == "/":
            result.append(line[i:])
            break

        if line[i] == "/":
            j = i + 1
            in_class = False

            while j < n:
                c = line[j]

                if c == "\\":
                    j += 2
                    continue

                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    j += 1

                    while j < n and line[j].isalpha():  # Flags
                        j += 1

                    result.append(" " * (j - i))
                    i = j
                    break

                j += 1
            else:
                result.append(line[i])
                i += 1
                continue

        else:
            result.append(line[i])
            i += 1

    return "".join(result)


# ----------------------------
# (3) Remove strings 
#   - '...'  "..."  `...`
#   - '''...'''  """..."""
#   - C# @"..." (verbatim)
# ----------------------------

def _escaped_by_backslash(line: str, i: int) -> bool:
   # True if quote at i is escaped by an odd number of backslashes before it.
   k = i - 1
   count = 0
   while k >= 0 and line[k] == "\\":
       count += 1
       k -= 1
   return (count % 2) == 1


def _is_dict_key_string(line: str, start_quote: int, end_quote: int) -> bool:
   """
   Treat keys like "rows": or 'rows': as a dict/object key and keep it.
   """
   j = end_quote + 1
   while j < len(line) and line[j].isspace():
       j += 1
   return j < len(line) and line[j] == ":"


def _find_quote_end(line: str, start: int, quote: str) -> int:
   """
   Find closing quote for a normal '...' or "..." string on the same line.
   Returns index of closing quote or -1 if not found.
   """
   i = start + 1
   while i < len(line):
       if line[i] == quote and not _escaped_by_backslash(line, i):
           return i
       i += 1
   return -1


def _should_keep_key_text(key_text: str) -> bool:
   """
   Only keep key strings that are style/presentation heuristics.
   Drop numeric keys like "9": and unrelated keys.
   """
   t = key_text.strip()
   if t.isdigit():
       return False  # "9": should not be kept

   keep = {k.lower() for k in (STYLE_KEYWORDS | PRESENTATION_KEYWORDS)}
   return t.lower() in keep


def remove_strings(line: str, language: str, state: StringState) -> str:
   out = ""
   i = 0
   n = len(line)


   while i < n:
       # ============================================================
       # (A) If we are currently inside a multi-line string
       # ============================================================
       if state.in_string:
           # Python triple-quote closers
           if state.mode == "PY_TRIPLE_SINGLE" and line.startswith("'''", i):
               state.in_string = False
               state.mode = "NONE"
               i += 3
               continue


           if state.mode == "PY_TRIPLE_DOUBLE" and line.startswith('"""', i):
               state.in_string = False
               state.mode = "NONE"
               i += 3
               continue


           # C# verbatim closer/escape: "" is escaped quote
           if state.mode == "CSHARP_VERBATIM":
               if line[i] == '"':
                   if i + 1 < n and line[i + 1] == '"':
                       i += 2  # escaped ""
                       continue
                   state.in_string = False
                   state.mode = "NONE"
                   i += 1
                   continue
               i += 1
               continue


           # Normal single/double closers
           if state.mode == "SINGLE":
               if line[i] == "'" and not _escaped_by_backslash(line, i):
                   state.in_string = False
                   state.mode = "NONE"
                   i += 1
                   continue
               i += 1
               continue


           if state.mode == "DOUBLE":
               if line[i] == '"' and not _escaped_by_backslash(line, i):
                   state.in_string = False
                   state.mode = "NONE"
                   i += 1
                   continue
               i += 1
               continue


           if state.mode == "BACKTICK":
               if line[i] == "`" and not _escaped_by_backslash(line, i):
                   state.in_string = False
                   state.mode = "NONE"
                   i += 1
                   continue
               i += 1
               continue

           i += 1
           continue


       # ============================================================
       # (B) If we are not inside a string: Check openers
       # ============================================================


       # Python triple quotes 
       if line.startswith("'''", i):
           state.in_string = True
           state.mode = "PY_TRIPLE_SINGLE"
           i += 3
           continue


       if line.startswith('"""', i):
           state.in_string = True
           state.mode = "PY_TRIPLE_DOUBLE"
           i += 3
           continue


       # C# verbatim opener: @"  
       if language == "csharp" and line.startswith('@"', i):
           state.in_string = True
           state.mode = "CSHARP_VERBATIM"
           i += 2
           continue


       # Template literal: `...` 
       if language in {"javascript", "typescript"} and line[i] == "`":
           end = line.find("`", i + 1)
           if end == -1:
               # No closer on this line: Drop rest of line 
               return out
           # Drop from ` to closing `
           i = end + 1
           continue


       # Normal single-quote
       if line[i] == "'":
           end = _find_quote_end(line, i, "'")
           if end != -1:
               # Closed on this line
               if _is_dict_key_string(line, i, end):
                   key_text = line[i + 1 : end]  # Inside quotes
                   if _should_keep_key_text(key_text):
                       out += line[i : end + 1]  # Keep key string only
               # else: drop the whole string
               i = end + 1
               continue


           return out


       # Normal double-quote
       if line[i] == '"':
           end = _find_quote_end(line, i, '"')
           if end != -1:
               # Closed on this line
               if _is_dict_key_string(line, i, end):
                   key_text = line[i + 1 : end]  # Inside quotes
                   if _should_keep_key_text(key_text):
                       out += line[i : end + 1]  # Keep key string only
               # else: drop the whole string
               i = end + 1
               continue


           return out


       # ============================================================
       # (C) Normal character
       # ============================================================
       out += line[i]
       i += 1


   return out


# ----------------------------
# (4) Cut single-line comments 
# ----------------------------

def remove_single_line_comment(line: str, language: str) -> str:
    # // always
    pos = line.find("//")
    if pos != -1:
        line = line[:pos]

    # # only for certain languages (Avoid breaking #define in C/C++)
    if language in HASH_COMMENT_LANGS:
        pos = line.find("#")
        if pos != -1:
            line = line[:pos]

    return line


# ---------------------------------
# (5) Presentation block detection
# ---------------------------------

def update_style_block_state(line: str, language: str, state: StyleBlockState) -> None:
    if language not in {"javascript", "typescript"}:
        return

    open_braces = line.count("{")
    close_braces = line.count("}")

    if state.in_style_block:
        state.brace_depth += open_braces - close_braces
        if state.brace_depth <= 0:
            state.in_style_block = False
            state.brace_depth = 0
        return

    if any(opener in line for opener in PRESENTATION_BLOCK_OPENERS):
        state.in_style_block = True
        state.brace_depth = open_braces - close_braces
        if state.brace_depth <= 0:
            state.in_style_block = False
            state.brace_depth = 0


# ----------------------------------
# (6) Constant definition detection 
# ----------------------------------

def is_pure_constant_definition(line: str, language: str) -> Dict[str, Any]:
    patterns = CONST_DEF_PATTERNS_BY_LANG.get(language)
    if not patterns:
        return {"is_const_def": False, "rhs_text": None, "rhs_start": None, "rhs_end": None}

    for rx in patterns:
        m = rx.match(line)
        if m:
            rhs_text = m.group(2)
            rhs_start, rhs_end = m.span(2)  # Literal position RHS in line
            return {
                "is_const_def": True,
                "rhs_text": rhs_text,
                "rhs_start": rhs_start,
                "rhs_end": rhs_end,
            }

    return {"is_const_def": False, "rhs_text": None, "rhs_start": None, "rhs_end": None}


# -------------------------------------------------
# (7) Skip if it is a non-logic content
# -------------------------------------------------

def is_html_text_content(line: str) -> bool:
    s = line.strip()

    if not s:
        return False

    # Match HTML text node like:
    # <td>2023/09/09</td>
    # <p>Step 1</p>
    if re.search(r">[^<{]*[A-Za-z0-9][^<{]*<", s):
        return True

    return False


def is_svg_vector_content(line: str) -> bool:
    s = line.strip()

    # Match standalone SVG path fragments like:
    # c-0.9,0.6-1.8,0.9
    # M76.2,90
    # L 12,34
    return bool(
        re.match(
            r'^[MmLlHhVvCcSsQqTtAa]\s*[-+]?(?:\d|\.\d)',
            s
        )
    )


# ----------------------------------------
# (8) Filters used after number detection
# ----------------------------------------

def is_http_status_code(match):
    try:
        return int(match.group()) in HTTP_STATUS_CODES
    except:
        return False


def is_http_status_context(line: str, match) -> bool:
    if not is_http_status_code(match):
        return False

    prefix = line[:match.start()].lower()

    return (
        "return" in line
        or ".status(" in prefix
        or "status(" in prefix
    )


def is_http_status_object_context(line: str, match) -> bool:
    if not is_http_status_code(match):
        return False

    prefix = line[:match.start()].lower()

    return (
        "status:" in prefix or
        '"status":' in prefix or
        "'status':" in prefix or
        "statuscode" in prefix or
        "http_response_code(" in prefix
    )


def is_rgb_color_context(line: str, match) -> bool:
    prefix = line[:match.start()].lower()

    return (
        "rgbcolor(" in prefix
        or "rgb(" in prefix
    )


def is_object_key_number(line: str, match) -> bool:
    """
    Skip numbers that are used as object keys like:
      2: { ... }
      404: "Not Found"
    We consider it an object key if the next non-space char after the number is ':'.
    """
    suffix = line[match.end():]
    suffix = suffix.lstrip()
    return suffix.startswith(":")


def has_css_unit_after_number(line: str, match) -> bool:
    # Read a small suffix and strip leading spaces
    suffix = line[match.end(): match.end() + 10].lstrip()

    for unit in CSS_UNITS:
        if suffix.startswith(unit):
            return True

    return False


def is_presentation_call_context(line: str, match) -> bool:
    """
    Ignore numbers inside theming/styling calls like createTheme(...).
    """
    prefix = line[:match.start()]
    window = prefix[max(0, len(prefix) - 80):]  # Small lookback window

    for name in PRESENTATION_CALL_NAMES:
        if f"{name}(" in window:
            return True

    return False


def is_presentation_prop_brace(line: str, match) -> bool:
    prefix = line[:match.start()]
    window = prefix[max(0, len(prefix) - 80):].lower()

    candidates = {k.lower() for k in STYLE_KEYWORDS} | {k.lower() for k in PRESENTATION_KEYWORDS}

    for key in candidates:
        pattern = rf"{key}\s*=\s*\{{"
        if re.search(pattern, window):
            return True

    return False


def is_style_context(line: str, match, language: str) -> bool:
    """
    Examples:
      - padding: 8, marginTop: 12, width: 320
      - width=300, height=200
      - {"width": 300}, {'min_width': 10}
    """
    window = LOOKBACK_WINDOW
    if "{" in line or ":" in line or "=" in line:
        window = max(window, 120)

    start = max(0, match.start() - window)
    prefix = line[start:match.start()].lower()

    for key in STYLE_KEYWORDS:
        if f"{key.lower()}:" in prefix:
            return True

    for key in PRESENTATION_KEYWORDS:
        k = key.lower()

        # key: 8
        if f"{k}:" in prefix:
            return True

        # key = 8
        if f"{k}=" in prefix:
            return True

        # "key": 8  or  'key': 8
        if f'"{k}":' in prefix or f"'{k}':" in prefix:
            return True

    return False