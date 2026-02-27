# Useless Parentheses Detection
#
# Scope:
#   This detector only analyzes parentheses around a binary expression when:
#     - The outer node is a binary expression, AND
#     - The inner node (inside the parentheses) is also a binary expression, AND
#     - Both nodes use the same Tree-sitter node type:
#         Java / JavaScript / TypeScript: "binary_expression"
#
#   Languages whose expression operators are represented using different node types
#   are currently excluded to avoid inconsistent behavior.
#   Example (Python Tree-sitter node type):
#     - binary_operator        (e.g., *, +)
#     - comparison_operator    (e.g., <, ==)
#     - boolean_operator       (e.g., and, or)
#
# Definitions:
#   A binary expression uses two operands and one operator.
#   Example: a + b  (operands: a, b; operator: +)
#
# How it works:
#   We use Tree-sitter to locate parenthesized_expression nodes whose outer and
#   inner expression are both binary_expression nodes.
#
#   Then we use an operator precedence table to decide if the parentheses are redundant.
#
# Rule:
#   Flag as useless parentheses if:
#     precedence(op_inner) > precedence(op_outer)
#   because the inner operator already binds tighter than the outer operator,
#   so parentheses do not change evaluation order.
#
# Example (flagged):
#   x = a + (b * c)
#   Tree-sitter:
#     binary_expression (+)            -> outer operator node "+"
#       left: a
#       right: parenthesized_expression
#               binary_expression (*)  -> inner operator node "*"
#       Since prec(*) > prec(+), parentheses are redundant -> FLAG
#
# Example (NOT flagged):
#   x = (a + b) * c
#   Here prec(+) < prec(*), parentheses change grouping -> DO NOT FLAG

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from tree_sitter import Node

from src.parsing.ts_parser import (guess_lang, inner_expression_of_parenthesized, node_text, parse_code, walk,)

# ============================================================
# Data Model
# ============================================================
@dataclass(frozen=True)
class UselessParenthesesViolation:
    pr_id: int
    file_path: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    outer_op: str
    inner_op: str
    reason: str
    code_snippet: str

def precedence(op: str, table: Dict[str, int]) -> Optional[int]:
    """Look up operator precedence from table. Returns None if operator not found."""
    return table.get(op)


def should_flag_useless_parens_binary(outer_op: str, inner_op: str, table: Dict[str, int]) -> bool:
    """
    Binary rule: Flag if inner operator has higher precedence than outer operator.
    (If we cannot determine precedence, do not flag.)
    """
    p_outer = precedence(outer_op, table)
    p_inner = precedence(inner_op, table)
    if p_outer is None or p_inner is None:
        return False
    return p_inner > p_outer

# Helper for CSV Output
def extract_context_window(code: str, center_line_1b: int, before: int = 5, after: int = 5) -> str:
    """
    Return a code snippet around center line (1-based):
    includes [center-before ... center ... center+after] with line numbers.
    """
    lines = code.splitlines()
    if not lines:
        return ""

    start_idx = max(0, center_line_1b - 1 - before)
    end_idx = min(len(lines), center_line_1b + after)

    width = len(str(end_idx))
    out_lines: List[str] = []
    for i in range(start_idx, end_idx):
        line_num = str(i + 1).rjust(width)
        out_lines.append(f"{line_num} | {lines[i]}")
    return "\n".join(out_lines)


# ============================================================
# Language Configurations
# ============================================================
@dataclass(frozen=True)
class LangBinaryConfig:
    lang: str
    precedence: Dict[str, int]
    paren_node_type: str = "parenthesized_expression"
    binary_node_type: str = "binary_expression"

# ============================================================
# Operator Precedence Tables:  Higher number = Binds tighter
# ============================================================
JS_TS_EXTS: Tuple[str, ...] = (".ts", ".js")

# Based on ECMAScript spec / MDN
JS_TS_PRECEDENCE: Dict[str, int] = {
    "*": 13,    "/": 13,    "%": 13,    "+": 12,    "-": 12,    "<<": 11,
    ">>": 11,   ">>>": 11,  "<": 10,    ">": 10,    "<=": 10,   ">=": 10,
    "instanceof": 10,       "==": 9,    "!=": 9,    "===": 9,   "!==": 9,
    "&": 8,     "^": 7,     "|": 6,     "&&": 5,    "||": 4,
}

# Based on the Java Language Specification
JAVA_PRECEDENCE: Dict[str, int] = {
    "*": 14,    "/": 14,    "%": 14,    "+": 13,    "-": 13,    "<<": 12,   
    ">>": 12,   ">>>": 12,  "<": 11,    "<=": 11,   ">": 11,    ">=": 11,
    "instanceof": 11,       "==": 10,   "!=": 10,   "&": 9, 
    "^": 8,     "|": 7,     "&&": 6,    "||": 5,
}

LANG_CONFIGS: Dict[str, LangBinaryConfig] = {
    "javascript": LangBinaryConfig(lang="javascript", precedence=JS_TS_PRECEDENCE),
    "typescript": LangBinaryConfig(lang="typescript", precedence=JS_TS_PRECEDENCE),
    "java": LangBinaryConfig(lang="java", precedence=JAVA_PRECEDENCE),
}


def is_js_ts_file(file_path: str) -> bool:
    """Check if file is JavaScript or TypeScript based on extension."""
    return file_path.lower().endswith(JS_TS_EXTS)


# ============================================================
# Operator extraction 
# ============================================================

def get_binary_operator(node: Node, code: str, table: Dict[str, int]) -> Optional[str]:
    """
    Extract operator token from a binary_expression node by:
      1) Scanning non-named token children
      2) Fallback to child_by_field_name("operator")

    Example:
    binary_expression                             binary_expression
    ├── identifier    ← Named                     ├── left: identifier
    ├── "+"           ← NOT named (Raw token)     ├── operator: "+"  ← Grammar defines operator field
    └── identifier    ← Named                     └── right: identifier

    """
    for child in node.children:
        if child.is_named:
            continue
        tok = node_text(code, child).strip()
        if tok in table:
            return tok

    op_child = node.child_by_field_name("operator")
    if op_child is not None:
        tok = node_text(code, op_child).strip()
        if tok in table:
            return tok

    return None


# ============================================================
# Detector
# ============================================================
def detect_useless_parentheses_binary_precedence(*, code: str, file_path: str, pr_id: int, cfg: LangBinaryConfig,
) -> List[UselessParenthesesViolation]:
    """
      P = parenthesized_expression
      E = inner expression of P
      Parent (outer expression) must be binary_expression
      E must be binary_expression
      Flag if prec(inner_op) > prec(outer_op)
    """
    parsed = parse_code(code, lang=cfg.lang, path=file_path)
    out: List[UselessParenthesesViolation] = []

    for paren in walk(parsed.tree.root_node):
        if paren.type != cfg.paren_node_type:
            continue

        inner = inner_expression_of_parenthesized(paren)
        if inner is None:
            continue

        if inner.type != cfg.binary_node_type:
            continue

        parent = paren.parent
        if parent is None or parent.type != cfg.binary_node_type:
            continue

        outer_op = get_binary_operator(parent, code, cfg.precedence)
        inner_op = get_binary_operator(inner, code, cfg.precedence)
        if not outer_op or not inner_op:
            continue

        if not should_flag_useless_parens_binary(outer_op, inner_op, cfg.precedence):
            continue

        (sr, sc) = paren.start_point
        (er, ec) = paren.end_point
        start_line = sr + 1
        end_line = er + 1

        out.append(
            UselessParenthesesViolation(
                pr_id=pr_id,
                file_path=file_path,
                start_line=start_line,
                start_col=sc + 1,
                end_line=end_line,
                end_col=ec + 1,
                outer_op=outer_op,
                inner_op=inner_op,
                reason="INNER_HIGHER_PRECEDENCE_THAN_OUTER",
                code_snippet=extract_context_window(code, start_line, before=5, after=5),
            )
        )

    return out


def detect_useless_parentheses_in_code(*, code: str, file_path: str, pr_id: int) -> List[UselessParenthesesViolation]:
    lang = guess_lang(file_path)

    if lang not in {"javascript", "typescript", "java"}:
        return []

    cfg = LANG_CONFIGS.get(lang)
    if cfg is None:
        return []

    return detect_useless_parentheses_binary_precedence(
        code=code,
        file_path=file_path,
        pr_id=pr_id,
        cfg=cfg,
    )
