import pytest
import pandas as pd
import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.preprocessing import normalize_name, simplify_name, name_key, parse_name

class TestPreprocessing:
    def test_normalize_name(self):
        assert normalize_name("  John   Doe  ") == "john doe"
        assert normalize_name("Alice") == "alice"
        assert normalize_name("Juan Martín del Potro") == "juan potro" # First + Last tokens
        assert normalize_name(123) == ""
        assert normalize_name(None) == ""
        assert normalize_name("Élève") == "eleve"

    def test_simplify_name(self):
        assert simplify_name("Jean-Luc Picard") == "jean luc picard"
        assert simplify_name("O'Connor") == "oconnor"
        assert simplify_name("  Spaces  ") == "spaces"
        assert simplify_name("Dr. Who") == "dr who"

    def test_name_key(self):
        assert name_key("John", "Doe") == "john doe"
        assert name_key("Jean-Luc", "Picard") == "jean luc picard"

    def test_parse_name(self):
        # Result is a pd.Series
        res = parse_name("John Doe")
        assert res["first_name"] == "John"
        assert res["last_name"] == "Doe"

        res = parse_name("Madonna")
        assert res["first_name"] == "Madonna"
        assert pd.isna(res["last_name"])

        res = parse_name("")
        assert res["first_name"] is None
        assert res["last_name"] is None
        
        res = parse_name(None)
        assert res["first_name"] is None
        assert res["last_name"] is None

        res = parse_name("John Middle Doe")
        assert res["first_name"] == "John"
        assert res["last_name"] == "Doe"
