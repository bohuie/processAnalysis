import os
import sys
import pytest

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the functions to test
from src.violations.magic_number_check import (
    MagicNumberConfig,
    detect_magic_numbers_from_code,
    count_magic_numbers_from_code,
)


class TestMagicNumberCheckBasics:
    """Test suite for basic MagicNumberCheck behavior"""

    def test_flags_simple_integer_literal_in_expression(self):
        """Test that a simple integer literal in an expression is flagged"""
        code = "return 24 * days;"
        findings = detect_magic_numbers_from_code(code)
        assert len(findings) == 1
        assert findings[0].literal == "24"
        assert findings[0].line_no == 1

    def test_flags_float_literal_in_expression(self):
        """Test that a float literal in an expression is flagged"""
        code = "price_after_tax = 1.05 * price"
        findings = detect_magic_numbers_from_code(code)
        assert len(findings) == 1
        assert findings[0].literal == "1.05"

    def test_ignores_trivial_numbers_by_default(self):
        """Test that default ignored numbers (0 and 1) are not flagged"""
        code = "\n".join([
            "if (x == 0) { return 1; }",
            "count = count + 1;",
        ])
        findings = detect_magic_numbers_from_code(code)
        assert len(findings) == 0

    def test_counts_findings_correctly(self):
        """Test that count helper returns the same count as detection output"""
        code = "\n".join([
            "return 24 * days;",
            "return 7 * weeks;",
        ])
        findings = detect_magic_numbers_from_code(code)
        count = count_magic_numbers_from_code(code)
        assert count == len(findings)
        assert count == 2


class TestMagicNumberCheckConstantHandling:
    """Test suite for ignoring literals in constant declarations"""

    def test_ignores_java_style_constant_declaration(self):
        """Test that literals in Java-like constant declarations are ignored by default"""
        code = "\n".join([
            "static final int HOURS_PER_DAY = 24;",
            "return HOURS_PER_DAY * days;",
        ])
        findings = detect_magic_numbers_from_code(code)
        # The constant declaration line is ignored; there should be no findings
        assert len(findings) == 0

    def test_can_flag_literals_in_constant_declaration_when_configured(self):
        """Test that literals in constant declarations can be flagged if configured"""
        code = "static final int HOURS_PER_DAY = 24;"
        cfg = MagicNumberConfig(ignore_in_constant_declarations=False)
        findings = detect_magic_numbers_from_code(code, config=cfg)
        assert len(findings) == 1
        assert findings[0].literal == "24"


class TestMagicNumberCheckAnnotationHandling:
    """Test suite for ignoring literals in annotations"""

    def test_ignores_annotation_line_by_default(self):
        """Test that annotation lines are ignored by default"""
        code = "\n".join([
            "@Size(10)",
            "String name = input;",
        ])
        findings = detect_magic_numbers_from_code(code)
        assert len(findings) == 0

    def test_can_flag_literals_in_annotations_when_configured(self):
        """Test that annotation literals can be flagged if configured"""
        code = "@Size(10)"
        cfg = MagicNumberConfig(ignore_in_annotations=False)
        findings = detect_magic_numbers_from_code(code, config=cfg)
        assert len(findings) == 1
        assert findings[0].literal == "10"


class TestMagicNumberCheckNegativeNumbers:
    """Test suite for handling negative numeric literals"""

    def test_flags_negative_literal_by_default(self):
        """Test that negative literals are detected as a single literal by default"""
        code = "return -5;"
        findings = detect_magic_numbers_from_code(code)
        assert len(findings) == 1
        assert findings[0].literal == "-5"

    def test_can_ignore_negative_literal_if_added_to_ignored_numbers(self):
        """Test that negative literals can be ignored if configured in ignored_numbers"""
        code = "return -1;"
        cfg = MagicNumberConfig(ignored_numbers={"0", "1", "-1"})
        findings = detect_magic_numbers_from_code(code, config=cfg)
        assert len(findings) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
