"""
Rule registry for Magic Number detection.

Purpose
-------
This module defines the semantic rule layer for Magic Number detection.

The detector identifies numeric literals and classifies their structural context.
This registry formalizes those contexts as stable rule identifiers and attaches:

- A human-readable name
- A description of the violation
- A clean-code rationale

This separation achieves:

1. Reproducibility of rule definitions
2. Stable rule IDs for analytics
3. Explicit clean-code justification
4. Extensibility for future code analytics rules

"""

from dataclasses import dataclass
from typing import Dict


# ============================================================
# Rule Model
# ============================================================

@dataclass(frozen=True)
class MagicNumberRule:
    rule_id: str
    name: str
    description: str
    rationale: str


# ============================================================
# Rule Definitions
# ============================================================

RULES: Dict[str, MagicNumberRule] = {

    # ------------------------------------------------------------
    # 1. Function / Method Argument
    # ------------------------------------------------------------
    "CALL_ARG": MagicNumberRule(
        rule_id="CALL_ARG",
        name="Magic Number in Function Argument",
        description=(
            "Numeric literal used directly as a function or method argument."
        ),
        rationale=(
            "Hard-coded argument values often represent policy decisions "
            "(e.g., timeout duration, retry count, limit size). "
            "Naming them as constants improves readability and reduces "
            "maintenance risk when such values change."
        ),
    ),

    # ------------------------------------------------------------
    # 2. Threshold Comparison
    # ------------------------------------------------------------
    "THRESHOLD": MagicNumberRule(
        rule_id="THRESHOLD",
        name="Magic Number in Comparison",
        description=(
            "Numeric literal used in a comparison expression "
            "(>, <, >=, <=, ==, !=)."
        ),
        rationale=(
            "Threshold values hide domain meaning and make decision logic "
            "harder to understand. Extracting them into named constants "
            "makes intent explicit and improves clarity."
        ),
    ),

    # ------------------------------------------------------------
    # 3. Loop Boundary
    # ------------------------------------------------------------
    "LOOP_BOUND": MagicNumberRule(
        rule_id="LOOP_BOUND",
        name="Magic Number in Loop Boundary",
        description=(
            "Numeric literal used to control loop iteration bounds."
        ),
        rationale=(
            "Loop limits often represent domain-specific constraints "
            "(e.g., number of retries, number of months). "
            "Using named constants improves maintainability and "
            "prevents duplication errors."
        ),
    ),

    # ------------------------------------------------------------
    # 4. Assignment
    # ------------------------------------------------------------
    "ASSIGNMENT": MagicNumberRule(
        rule_id="ASSIGNMENT",
        name="Magic Number in Assignment",
        description=(
            "Numeric literal assigned directly to a variable "
            "without being declared as a constant."
        ),
        rationale=(
            "Assigned numeric values often represent configuration "
            "or policy parameters. If not declared as constants, "
            "they reduce clarity and increase the risk of inconsistent updates."
        ),
    ),

    # ------------------------------------------------------------
    # 5. Generic Fallback
    # ------------------------------------------------------------
    "GENERIC": MagicNumberRule(
        rule_id="GENERIC",
        name="Generic Magic Number",
        description=(
            "Numeric literal detected outside known safe cases "
            "and not classified into a more specific context."
        ),
        rationale=(
            "Unexplained numeric literals reduce clarity and may "
            "introduce hidden coupling between logic and values. "
            "Even when not structurally critical, naming improves readability."
        ),
    ),
}


# ============================================================
# Access Helper
# ============================================================

def get_rule(rule_id: str) -> MagicNumberRule:
    """
    Retrieve a rule definition by its rule_id.

    Raises:
        KeyError: If the rule_id is not registered.

    This ensures:
    - Stable rule references
    - Early failure if classifier returns an undefined rule
    """
    if rule_id not in RULES:
        raise KeyError(f"Unknown MagicNumber rule_id: {rule_id}")
    return RULES[rule_id]