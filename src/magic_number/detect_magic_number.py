"""
Magic Number Detector

A magic number is a hard-coded numeric literal used directly in code
instead of a named constant. That numeric literal lacks a descriptive name, 
its meaning is unclear, and the value becomes harder to maintain or modify.

Example:

Bad:
timeout = 300

Better:
const DEFAULT_TIMEOUT = 300
timeout = DEFAULT_TIMEOUT

This module implements the main detection pipeline that scans source code
for magic numbers.

Overview:

1. Language resolution
   - Determine programming language from file extension when language="auto".

2. File filtering
   - Skip unsupported file types and paths filtered by should_skip_file().

3. Line preprocessing
   - Remove block comments, regex literals, strings, and single-line comments.

4. Context tracking
   - Maintain state for block comments, strings, and presentation/style blocks.

5. Structural checks
   - Detect constant definitions and skip non-logic content (HTML/SVG).

6. Numeric detection
   - Identify numeric literals using NUMERIC_RE.

7. Context filtering
   - Skip numbers that belong to safe literals, HTTP status codes,
     object keys, CSS units, presentation props, styling contexts,
     RGB colors, or constant definitions.

8. Reporting
   - Remaining numbers are recorded as magic number violations.

Scope:
The detector focuses on numbers used in logical programming behavior
(e.g., conditions, algorithm parameters, timeouts, limits).

Styling and layout values are intentionally excluded. If new styling
patterns appear in future frameworks, they may need to be manually
added to the pattern configuration to keep the detector accurate.
"""

from typing import List, Dict, Any
from pathlib import Path

from .magic_number_patterns import NUMERIC_RE, SAFE_LITERALS, EXT_TO_LANG
from src.magic_number.magic_number_filter import (
    should_skip_file,
    CommentState,
    StringState,
    StyleBlockState,
    remove_block_comments,
    remove_strings,
    remove_single_line_comment,
    remove_regex_literals,
    update_style_block_state,
    is_pure_constant_definition,
    has_css_unit_after_number,
    is_presentation_call_context,
    is_style_context,
    is_presentation_prop_brace,
    is_object_key_number, 
    is_http_status_code,
    is_http_status_context,
    is_html_text_content,
    is_svg_vector_content,
    is_http_status_object_context,
    is_rgb_color_context,
)


def infer_language_from_path(file_path: str) -> str:
    """
    Determines programming language from file extension.
    """
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LANG.get(ext, "generic")


def detect_magic_numbers(code: str, file_path: str, language: str) -> List[Dict[str, Any]]:

    # Allow runner to pass language="auto"
    if not language or language == "auto":
        language = infer_language_from_path(file_path)

    # Skip unknown file types (e.g., .md, .json)
    if language == "generic":
        return []

    if should_skip_file(file_path):
        return []

    comment_state = CommentState()                      # Not inside block comment
    string_state = StringState()                        # Not inside string
    style_state = StyleBlockState()                     # Not inside presentation block

    violations: List[Dict[str, Any]] = []

    for line_no, raw_line in enumerate(code.splitlines(), start=1):
        line = raw_line

        # (1) Remove block comments
        line = remove_block_comments(line, comment_state)

        # (2) Remove regex literals
        line = remove_regex_literals(line, language)

        # (3) Remove strings
        line = remove_strings(line, language, string_state)

        # (4) Remove single-line comments
        line = remove_single_line_comment(line, language)

        # (5) Skip full presentaion blocks
        update_style_block_state(line, language, style_state)
        if style_state.in_style_block:
            continue

        # (6) Constant definition detection
        const_info = is_pure_constant_definition(line, language)
        rhs_text = const_info["rhs_text"] if const_info["is_const_def"] else None
        rhs_start = const_info.get("rhs_start")
        rhs_end = const_info.get("rhs_end")

        # (7) Skip if it is a non-logic content
        if is_html_text_content(line):
            continue

        if is_svg_vector_content(line):
            continue

        # (8) Detect numbers → Apply filters
        for match in NUMERIC_RE.finditer(line):
            literal = match.group()

            # Skip safe literals
            if literal in SAFE_LITERALS:
                continue

            if is_http_status_code(match) and "return" in line:
                continue        

            # Skip HTTP status codes in response contexts
            if is_http_status_context(line, match):
                continue  

            # Skip HTTP status codes in object literals
            if is_http_status_object_context(line, match):
                continue
            
            # Skip RGB color context
            if is_rgb_color_context(line, match):
                continue

            # Skip numeric object keys like "2:"
            if is_object_key_number(line, match):
                continue

            # Skip constant RHS literal
            if (
                rhs_text is not None
                and rhs_start is not None
                and rhs_end is not None
                and literal == rhs_text
                and match.start() >= rhs_start
                and match.end() <= rhs_end
            ):
                continue

            # Skip css unit numbers
            if has_css_unit_after_number(line, match):
                continue

            # Skip theming/styling function calls
            if is_presentation_call_context(line, match):
                continue

            # Skip JSX presentation props (size={24}, width={300}, etc.)
            if is_presentation_prop_brace(line, match):
                continue

            # Skip style/presentation keyword contexts
            if is_style_context(line, match, language):
                continue

            violations.append({
                "file": file_path,
                "line": line_no,
                "literal": literal,
                "line_text": raw_line.strip(),
            })

    return violations