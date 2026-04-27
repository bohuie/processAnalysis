"""
Magic Number Pattern Configurations

This module defines configuration rules used by the magic number detector,
including file skipping rules, language mappings, numeric literal patterns,
constant definitions, and heuristics for filtering numbers that appear in 
non-logical contexts (e.g., styling values, HTTP status codes, and CSS units).

Usage:
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
"""

import re

# ========================================
# FILE SKIPPING
# ========================================

FORMAT_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less", ".html", ".htm"
}

STYLE_FOLDERS = {
    "/styles/",
    "/style/",
    "/theme/",
    "/themes/",
    "/css/",
    "/scss/",
}

# Skip files that contain third-party code, generated artifacts, or non-logical content
EXCLUDED_PATH_KEYWORDS = {
    "site-packages", "node_modules", "vendor", "dist", "build",
    "venv", ".venv", "__pycache__",
    ".next", ".nuxt", "coverage", "bootstrap", "test", "tests", "docs",
    ".open-next", "_next/static", "/assets/",
}

# ========================================
# LANGUAGE SETTINGS
# ========================================

# These languages treat '#' as a single-line comment
HASH_COMMENT_LANGS = {"python", "ruby", "php"}

# File Formats with pattern configuration
EXT_TO_LANG = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
    ".java": "java",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".php": "php",
    ".rb": "ruby",
}

# ========================================
# SAFE LITERALS
# ========================================

SAFE_LITERALS = {"-1", "0", "1", "2"}

# HTTP constant numbers (status codes)
HTTP_STATUS_CODES = {
    # Success
    200, 201, 202, 203, 204, 205, 206,

    # Redirection
    300, 301, 302, 303, 304, 307, 308,

    # Client errors
    400, 401, 402, 403, 404, 405, 406,
    408, 409, 410, 412, 413, 415,
    422, 429,

    # Server errors
    500, 501, 502, 503, 504, 505
}

# ========================================
# PRESENTATION / STYLING FUNCTION
# ========================================

PRESENTATION_CALL_NAMES = {
    "createTheme", "makeStyles", "createStyles",
}

# ========================================
# KEYWORDS 
# ========================================

# For skipping numbers in contexts like width=300, rows=10, {"height": 200}

PRESENTATION_BASE_KEYS = {
    "rows", "cols",
    "width", "height",
    "min_width", "max_width", "min_height", "max_height",
    "minWidth", "maxWidth", "minHeight", "maxHeight",
    "size", "radius", "spacing", "gap",
    "fontSize", "strokeWidth", "maxLength", "minLength", "maximumValue", "minimumValue",
    "xs", "sm", "md", "lg", "xl", "xxl", "level",
}

# For skipping numbers in contexts like padding: 8, marginTop: 12
STYLE_ONLY_KEYS = {
    "style", "sx", "viewBox",
    "x", "y", "cx", "cy", "r",
    "padding", "margin",
    "marginTop", "marginRight", "marginBottom", "marginLeft",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "borderRadius", "boxShadow",
    "minX", "minY",
    "m", "mt", "mr", "mb", "ml", "mx", "my",
    "p", "pt", "pr", "pb", "pl", "px", "py",
    "rowGap", "columnGap",
    "zIndex", "opacity",
    "lineHeight", "letterSpacing", "fontWeight",
}

PRESENTATION_KEYWORDS = set(PRESENTATION_BASE_KEYS)
STYLE_KEYWORDS = set(PRESENTATION_BASE_KEYS) | set(STYLE_ONLY_KEYS)

# Number of characters to look backward from a numeric literal
# when checking style/presentation context
LOOKBACK_WINDOW = 80

# ========================================
# CSS UNIT SUFFIXES
# ========================================

# For skipping numbers in contexts like 12px, 2rem, 50%
CSS_UNITS = {
    "px", "rem", "em", "%", "vh", "vw", "vmin", "vmax",
    "ch", "ex", "pt", "cm", "mm", "in", "pc",
    "ms", "s", "deg",
}

# ========================================
# NUMERIC LITERAL REGEX
# ========================================

NUMERIC_RE = re.compile(
    r"""
    (?<![\w$])
    -?
    (
        0[bB][01_]+ |
        0[xX][0-9a-fA-F_]+ |
        \d+\.\d+ |
        \d+
    )
    (?:[eE][+-]?\d+)?
    (?![\w$])
    """,
    re.VERBOSE,
)

# ========================================
# CONSTANT DEFINITION PATTERNS
# ========================================

CONST_DEF_PATTERNS_BY_LANG = {
    "javascript": [
        re.compile(r"^\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*(\d+)\s*;?\s*$"),
    ],
    "typescript": [
        re.compile(r"^\s*const\s+([A-Za-z_$][\w$]*)\s*=\s*(\d+)\s*;?\s*$"),
    ],
    "java": [
        re.compile(
            r"^\s*(?:public|private|protected)?\s*static\s+final\s+\w[\w<>\[\]]*\s+([A-Za-z_]\w*)\s*=\s*(\d+)\s*;?\s*$"
        ),
    ],
    "csharp": [
        re.compile(
            r"^\s*(?:public|private|protected|internal)?\s*const\s+\w[\w<>\[\]]*\s+([A-Za-z_]\w*)\s*=\s*(\d+)\s*;?\s*$"
        ),
    ],
    "cpp": [
        re.compile(r"^\s*constexpr\s+\w[\w:<>\*\&\s\[\]]*\s+([A-Za-z_]\w*)\s*=\s*(\d+)\s*;?\s*$"),
        re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+(\d+)\s*$"),
    ],
    "c": [
        re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+(\d+)\s*$"),
    ],
    "python": [
        re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*$"),
    ],
    "ruby": [
        re.compile(r"^\s*([A-Z][A-Za-z0-9_]*)\s*=\s*(\d+)\s*$"),
    ],
    "php": [
        re.compile(r"^\s*const\s+([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*;?\s*$"),
        re.compile(r'^\s*define\s*\(\s*["\']([A-Z][A-Z0-9_]*)["\']\s*,\s*(\d+)\s*\)\s*;?\s*$'),
    ],
}

# ========================================
# PRESENTATION BLOCK OPENERS 
# ========================================

# Blocks we want to ignore entirely
# Each opener implies we're entering a "{...}" block and we track brace depth until it closes.
PRESENTATION_BLOCK_OPENERS = (
    "sx={{",
    "style={{",
    "createTheme({", "StyleSheet.create({", 
    "createStyles({", "makeStyles({", "theme({",    
)  