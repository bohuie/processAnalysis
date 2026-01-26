"""
Violations module.

This package contains implementations of code-quality violation detectors.
Each detector is responsible for identifying one specific violation type
(e.g., MagicNumberCheck) using a testable and language-agnostic strategy.

Current violation detectors:
- MagicNumberCheck
"""

from .magic_number_check import (
    MagicNumberFinding,
    MagicNumberConfig,
    detect_magic_numbers_from_code,
    count_magic_numbers_from_code,
)

__all__ = [
    "MagicNumberFinding",
    "MagicNumberConfig",
    "detect_magic_numbers_from_code",
    "count_magic_numbers_from_code",
]
