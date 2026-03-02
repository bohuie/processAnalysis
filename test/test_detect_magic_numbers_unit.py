from __future__ import annotations

from typing import List

import pytest

from src.violations.detect_magic_numbers import detect_magic_numbers


def _lits(violations) -> List[str]:
    return [v.literal for v in violations]


def _ctxs(violations) -> List[str]:
    return [v.context_type for v in violations]


def _run(code: str, *, lang: str, path: str):
    return detect_magic_numbers(
        code,
        language=lang,
        file_path=path,
        pr_id=123,
        head_sha="deadbeef",
    )


def test_skips_safe_literals_0_and_1():
    code = "x = 0\ny = 1\nz = 2\n"
    v = _run(code, lang="python", path="a.py")
    assert _lits(v) == ["2"]


def test_detects_assignment_in_python():
    code = "x = 42\n"
    v = _run(code, lang="python", path="a.py")
    assert _lits(v) == ["42"]
    assert v[0].context_type in {"ASSIGNMENT", "GENERIC"}


def test_constant_definition_skipped_when_literal_only_python():
    code = "MAX_RETRIES = 5\nx = 5\n"
    v = _run(code, lang="python", path="a.py")
    assert _lits(v) == ["5"]


def test_constant_definition_not_skipped_when_expression_python():
    code = "MAX_RETRIES = get_limit(5)\n"
    v = _run(code, lang="python", path="a.py")
    assert "5" in _lits(v)
    assert "CALL_ARG" in _ctxs(v) or v[0].context_type in {"CALL_ARG", "GENERIC"}


def test_constant_definition_skipped_when_literal_only_js():
    code = "const MAX = 5;\nlet x = 5;\n"
    v = _run(code, lang="javascript", path="a.js")
    assert _lits(v) == ["5"]


def test_constant_definition_not_skipped_when_expression_js():
    code = "const MAX = getLimit(5);\n"
    v = _run(code, lang="javascript", path="a.js")
    assert _lits(v) == ["5"]


def test_call_argument_js():
    code = "fetch(url, 10);"
    v = _run(code, lang="javascript", path="sample.js")
    assert any(x.literal == "10" and x.context_type == "CALL_ARG" for x in v)


def test_threshold_js():
    code = "if (count > 7) { doThing(); }"
    v = _run(code, lang="javascript", path="sample.js")
    assert any(x.literal == "7" and x.context_type == "THRESHOLD" for x in v)


def test_loop_bound_js():
    code = "for (let i = 0; i < 12; i++) { sum += i; }"
    v = _run(code, lang="javascript", path="sample.js")
    assert any(x.literal == "12" and x.context_type == "LOOP_BOUND" for x in v)


def test_assignment_js():
    code = "timeout = 10;"
    v = _run(code, lang="javascript", path="sample.js")
    assert any(x.literal == "10" and x.context_type == "ASSIGNMENT" for x in v)


def test_typescript_supported_call_arg():
    code = "function f(x: number) { return g(x, 9); }"
    v = _run(code, lang="typescript", path="sample.ts")
    assert any(x.literal == "9" and x.context_type == "CALL_ARG" for x in v)


def test_python_ignores_ui_attrs_dict_rows_cols_line():
    code = (
        'description = forms.CharField(widget=forms.Textarea(attrs={"rows":5, "cols":23}))\n'
        "x = 9\n"
    )
    v = _run(code, lang="python", path="app/stream/forms.py")
    # attrs line ignored, so only "9" remains
    assert _lits(v) == ["9"]


def test_python_triple_quoted_string_masks_numbers_inside():
    code = (
        'text = """\n'
        "Version 1.2.6\n"
        "Copyright 2009\n"
        '"""\n'
        "x = 7\n"
    )
    v = _run(code, lang="python", path="a.py")
    assert _lits(v) == ["7"]


def test_js_multiline_block_comment_masks_version_numbers():
    # /*
    #  * @requires jQuery 1.2.6 or later
    #  * Copyright (c) 2009 ...
    #  */
    code = (
        "/*\n"
        " * Based on jQuery Formset 1.1\n"
        " * @requires jQuery 1.2.6 or later\n"
        " * Copyright (c) 2009, Someone\n"
        " */\n"
        "var x = 7;\n"
    )
    v = _run(code, lang="javascript", path="app/productionfiles/admin/js/inlines.js")
    # All numbers in the comment must be ignored. Only 7 remains
    assert _lits(v) == ["7"]
    assert v[0].context_type in {"ASSIGNMENT", "GENERIC"}


def test_js_single_line_line_comment_masks_numbers():
    code = "var x = 7; // requires v1.2.6\n"
    v = _run(code, lang="javascript", path="a.js")
    # Only "7" remains
    assert _lits(v) == ["7"]


def test_js_single_line_block_comment_masks_numbers():
    code = "var x = 7; /* v1.2.6 */\n"
    v = _run(code, lang="javascript", path="a.js")
    assert _lits(v) == ["7"]


def test_js_const_initializer_function_body_still_flags():
    code = """
    const X = () => retry(5);
    """
    v = _run(code, lang="javascript", path="sample.js")
    assert any(x.literal == "5" for x in v)


def test_jsx_style_object_ignored():
    code = """
    const X = () => (
      <Button style={{ marginRight: 8, borderRadius: 2 }}>Hi</Button>
    );
    """
    v = _run(code, lang="javascript", path="sample.jsx")
    assert not any(x.literal in {"8", "2"} for x in v)


def test_jsx_sx_object_ignored():
    code = """
    const X = () => (
      <Box sx={{ padding: 12, margin: 5 }} />
    );
    """
    v = _run(code, lang="javascript", path="sample.jsx")
    assert not any(x.literal in {"12", "5"} for x in v)


def test_jsx_viewbox_ignored():
    code = """
    const X = () => (
      <Icon viewBox={{ minX: 0, minY: 0, width: 4, height: 16 }} />
    );
    """
    v = _run(code, lang="javascript", path="sample.jsx")
    assert not any(x.literal in {"4", "16"} for x in v)


def test_create_theme_ignored():
    code = """
    import { createTheme } from "@aws-amplify/ui-react";
    export default createTheme({
      tokens: {
        colors: {
          red: {
            10: { value: "hsl(0, 75%, 95%)" }
          }
        }
      }
    });
    """
    v = _run(code, lang="javascript", path="theme.js")
    assert not any(x.literal == "10" for x in v)


def test_logic_inside_jsx_should_detect():
    code = """
    const X = () => (
      <Button onClick={() => retry(5)}>Retry</Button>
    );
    """
    v = _run(code, lang="javascript", path="sample.jsx")
    assert any(x.literal == "5" for x in v)


def test_skips_excluded_paths():
    code = "x = 9\n"
    v = _run(code, lang="python", path="node_modules/pkg/a.py")
    assert v == []


def test_java_file_extension_is_supported():
    code = "class A { void f(){ int x = 2; } }"
    v = _run(code, lang="java", path="A.java")
    assert any(x.literal == "2" for x in v)


def test_java_static_final_constant_literal_not_flagged():
    code = (
        "class A {\n"
        "  static final int MAX = 5;\n"
        "  void f(){ int x = MAX; }\n"
        "}\n"
    )
    v = _run(code, lang="java", path="A.java")
    assert not any(x.literal == "5" for x in v)


def test_java_final_static_constant_literal_not_flagged():
    code = (
        "class A {\n"
        "  final static int MAX = 5;\n"
        "  void f(){ int x = MAX; }\n"
        "}\n"
    )
    v = _run(code, lang="java", path="A.java")
    assert not any(x.literal == "5" for x in v)


def test_java_constant_with_expression_still_scans_and_flags():
    code = "class A { static final int MAX = getLimit(5); }"
    v = _run(code, lang="java", path="A.java")
    assert any(x.literal == "5" for x in v)

def test_java_hex_literal_not_detected_anywhere():
    code = """
    class Sample {
        void f() { foo(0xFF); }
    }
    """
    v = _run(code, lang="java", path="Sample.java")
    assert v == []


def test_java_binary_literal_not_detected_anywhere():
    code = """
    class Sample {
        void f() { foo(0b1010); }
    }
    """
    v = _run(code, lang="java", path="Sample.java")
    assert v == []
