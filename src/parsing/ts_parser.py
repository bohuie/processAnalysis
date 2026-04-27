# Parsing Layer
#
# Parsing is used to understand the structural syntax of the source code
# before applying the detection rule.
#
# We use Tree-sitter, which is:
#   - A parser generator tool
#   - An incremental parsing library
#
# Tree-sitter builds a Concrete Syntax Tree (CST) for a source file.
# This tree represents the grammatical structure of the code,
# preserving the exact structure defined by the language grammar.
#
# Our detector does NOT operate on raw text.
# Instead, it operates on syntax tree nodes 
# Example:
#   - parenthesized_expression
#   - binary_expression
#
# Code:
#     x = a + (b * c)
#
# Tree-sitter structure:
#
#     assignment_expression
#       ├── identifier (x)
#       └── binary_expression (+)       ← outer binary node
#             ├── identifier (a)
#             └── parenthesized_expression
#                   └── binary_expression (*)   ← inner binary node
#
# After parsing, we apply the rule to decide whether the case should be flagged or not.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from tree_sitter import Node, Tree
from tree_sitter_languages import get_parser


@dataclass(frozen=True)
class ParsedFile:
    path: str
    code: str
    tree: Tree

# Language routing
def guess_lang(file_path: str) -> Optional[str]:
    p = file_path.lower()
    if p.endswith(".java"):
        return "java"
    if p.endswith(".js") or p.endswith(".jsx"):
        return "javascript"
    if p.endswith(".ts") or p.endswith(".tsx"):
        return "typescript"
    if p.endswith(".py"):
        return "python"
    if p.endswith(".c") or p.endswith(".h"):
        return "c"
    if p.endswith(".cpp") or p.endswith(".hpp") or p.endswith(".cc"):
        return "cpp"
    return None

# Parse full source into a syntax tree
def parse_code(code: str, lang: str, path: str = "<memory>") -> ParsedFile:
    parser = get_parser(lang)
    tree = parser.parse(code.encode("utf-8"))
    return ParsedFile(path=path, code=code, tree=tree)


def parse_file(path: str) -> Optional[ParsedFile]:
    lang = guess_lang(path)
    if not lang:
        return None

    code = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_code(code, lang=lang, path=path)

# Traverse nodes
def walk(node: Node) -> Iterable[Node]:
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for child in reversed(n.children):
            stack.append(child)

# Extract the exact source substring covered by node
def node_text(code: str, node: Node) -> str:
    b = code.encode("utf-8")
    return b[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

# For a parenthesized_expression node, return the inner expression node.
def inner_expression_of_parenthesized(node: Node) -> Optional[Node]:
    if node.type != "parenthesized_expression":
        return None
    return node.named_children[0] if node.named_children else None