"""
Magic Number Detector — Configuration 
===========================================================

Purpose
-------
This module centralizes all configuration values, classification rules,
and scope control constants used throughout the magic number detector.

It defines:

    • Context classification labels (CALL_ARG, THRESHOLD, LOOP_BOUND, ASSIGNMENT, GENERIC)
    • Safe literals that should not be flagged
    • Supported programming languages and file extensions
    • Presentation/styling exclusions (JSX props, CSS units, UI keys)
    • Path exclusions for third party or generated code
    • Heuristics for identifying minified files
"""

from __future__ import annotations

from typing import Dict, Set, Tuple

RULES: Dict[str, Dict[str, str]] = {
    "CALL_ARG": {"name": "Magic Number in Function Argument", "description": "Used as a function/method argument."},
    "THRESHOLD": {"name": "Magic Number in Comparison", "description": "Used in a comparison expression."},
    "LOOP_BOUND": {"name": "Magic Number in Loop Boundary", "description": "Used to control loop bounds."},
    "ASSIGNMENT": {"name": "Magic Number in Assignment", "description": "Assigned directly to a variable."},
    "GENERIC": {"name": "Generic Magic Number", "description": "Detected but not classified more specifically."},
}

# Safe literals 
SAFE_LITERALS: Set[str] = {"0", "1"}

# Language filtering
ALLOWED_LANGS: Set[str] = {"javascript", "typescript", "python", "java"}
ALLOWED_EXTS: Tuple[str, ...] = (".js", ".jsx", ".ts", ".tsx", ".py", ".java")

# Common UI/layout property names where numbers are usually just formatting
PRESENTATION_PROP_NAMES: Set[str] = {
    "style", "sx", "viewBox", "width", "height", "minWidth", "maxWidth", "minHeight", "maxHeight",
    "x", "y", "cx", "cy", "r", "strokeWidth", "fontSize", "padding", "margin", "marginTop",
    "marginRight", "marginBottom", "marginLeft", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "borderRadius", "boxShadow", "minX", "minY", "m", "mt", "mr", "mb", "ml", "mx", "my", "p", "pt",
    "pr", "pb", "pl", "px", "py", "gap", "spacing", "rowGap", "columnGap", "zIndex", "opacity",
    "lineHeight", "letterSpacing", "fontWeight",
}

# Styling/theming function names (ignore numbers inside these)
PRESENTATION_CALL_NAMES: Set[str] = {
    "createTheme", "makeStyles", "createStyles",
}

# Python UI/layout keys commonly used for widget sizing
PY_PRESENTATION_KEYWORDS: Set[str] = {
    "rows", "cols", "width", "height", "min_width", "max_width", "min_height", "max_height",
}

# CSS unit suffixes
# Examples: 12px, 2rem, 50%
CSS_UNITS: Tuple[str, ...] = (
    "px", "rem", "em", "%", "vh", "vw", "vmin", "vmax", "ch", "ex", "pt", "cm", "mm", "in", "pc",
)

EXCLUDED_PATH_KEYWORDS: Set[str] = {
    "site-packages", "node_modules", "vendor", "dist", "build", "venv", ".venv", "__pycache__",
    ".next", ".nuxt", "coverage",
}

MAX_REASONABLE_LINE_LENGTH = 400
MAX_MINIFIED_LINE_RATIO = 0.5  # if >50% of lines are extremely long -> probably minified