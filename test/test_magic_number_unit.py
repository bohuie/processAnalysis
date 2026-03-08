"""
Test script for Magic Number Detector.

This script tests the detect_magic_numbers function to:
1. Verify magic numbers in logical code
2. Skip numbers inside comments, strings, regex, and constant definitions
3. Ignore presentation/styling contexts
4. Handle language-specific patterns
5. Ignore numeric literal in non-logic content (HTML text, SVG paths,
   HTTP status codes, RGB colors, and object keys)
"""

import pytest

from src.magic_number.detect_magic_number import detect_magic_numbers


def _lits(violations):
    return [v["literal"] for v in violations]


def test_skips_formatting_files_by_extension():
    code = "padding: 8px;\nmargin: 12px;\n"
    v = detect_magic_numbers(code, "src/styles/main.scss", "typescript")
    assert v == []


def test_skips_formatting_files_by_folder():
    code = "const x = 10;\n"
    v = detect_magic_numbers(code, "src/theme/colors.ts", "typescript")
    assert v == []


def test_skips_excluded_vendor_build_paths():
    code = "let x = 5;\n"
    v = detect_magic_numbers(code, "node_modules/pkg/index.ts", "typescript")
    assert v == []


def test_block_comment_multiline_removes_numbers_inside():
    code = """\
    /* threshold is 10
    do not change */
    let x = 5;
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["5"]


def test_string_single_and_double_quotes_remove_numbers_inside():
    code = """\
    const a = 'threshold 10';
    const b = "limit 20";
    const x = 5;
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert v == []


def test_js_backtick_template_string_skips_entire_template():
    code = """\
    const css = `margin-top: 8px; width: ${w}px;`;
    const x = 5;
    """
    v = detect_magic_numbers(code, "a.ts", "typescript")
    assert v == []


def test_python_triple_quotes_skip_multiline_string():
    code = '''\
    doc = """this is 10
    and 20"""
    x = 5
    '''
    v = detect_magic_numbers(code, "a.py", "python")
    assert _lits(v) == ["5"]


def test_csharp_verbatim_string_skips_escaped_double_quote():
    code = """\
    var s = @"number ""10"" inside";
    int x = 5;
    """
    v = detect_magic_numbers(code, "A.cs", "csharp")
    assert _lits(v) == ["5"]


def test_cut_single_line_comment_slash_slash_always():
    code = """\
    const x = 5; // threshold 10
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert v == []


def test_cut_single_line_comment_hash_only_for_python_php_ruby():
    # Python: # comment should be cut
    code_py = "x = 5  # threshold 10\n"
    v_py = detect_magic_numbers(code_py, "a.py", "python")
    assert _lits(v_py) == ["5"]

    # C++: # should NOT be cut 
    code_cpp = "#define MAX 10\nint x = 5;\n"
    v_cpp = detect_magic_numbers(code_cpp, "a.cpp", "cpp")
    assert _lits(v_cpp) == ["5"]


def test_style_block_sx_is_skipped_with_brace_depth():
    code = """\
    <Button
      sx={{
        marginTop: 8,
        padding: 12
      }}
    />
    const x = 5;
    """
    v = detect_magic_numbers(code, "Comp.tsx", "typescript")
    assert v == []


def test_style_context_keyword_skips_even_without_unit():
    code = "const styles = { padding: 8, marginTop: 12 };\nconst x = 5;\n"
    v = detect_magic_numbers(code, "a.ts", "typescript")
    assert v == []


def test_presentation_call_names_skip_numbers_inside_createTheme():
    code = """\
    const theme = createTheme({ spacing: 8, shape: { borderRadius: 12 } });
    let x = 5;
    """
    v = detect_magic_numbers(code, "a.ts", "typescript")
    assert _lits(v) == ["5"]


def test_css_unit_suffix_is_skipped():
    code = "let x = 8px; let y = 100%; let z = 1.5rem; let a = 5;\n"
    v = detect_magic_numbers(code, "a.ts", "typescript")
    assert _lits(v) == ["5"]


def test_const_definition_rhs_literal_only_is_skipped_but_other_numbers_remain():
    code = "const MAX = 5;\ndoThing(10);\n"
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_safe_literals_0_and_1_are_skipped():
    code = "x = 0\ny = 1\nz = 5\n"
    v = detect_magic_numbers(code, "a.py", "python")
    assert _lits(v) == ["5"]


def test_presentation_prop_brace_skips_size_number():
    code = """\
    <CircularProgress size={24} color="inherit" />
    let x = 5;
    """
    v = detect_magic_numbers(code, "Comp.tsx", "typescript")
    assert _lits(v) == ["5"]


def test_js_backtick_unclosed_does_not_wipe_following_jsx_lines():
    code = """\
    const s = `unterminated
    <Snackbar autoHideDuration={6000} />
    """
    v = detect_magic_numbers(code, "a.jsx", "javascript")
    assert "6000" in _lits(v)


def test_numeric_object_key_is_skipped():
    code = """\
    const heading = {
      1: { fontSize: 10 },
      2: { fontSize: 12 },
    };
    const x = 5;
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert v == []


def test_js_multiline_email_regex_numbers_skipped():
    code = r'''\
    const EMAIL_ADDRESS_REGEX =
      /^[-!#$%&'*+/0-9=?A-Z^_a-z`{|}~](.?[-!#$%&'*+/0-9=?A-Z^_a-z`{|}~])*@[a-zA-Z0-9](-*.?[a-zA-Z0-9])*.[a-zA-Z](-?[a-zA-Z0-9])+$/;
    doThing(10);
    '''
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_js_regex_with_slash_inside_char_class_is_skipped():
    code = r'''\
    const R =
      /^[a-z/0-9]+$/;
    doThing(10);
    '''
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_createTheme_block_is_skipped_numbers_inside_not_reported():
    code = """\
    import { createTheme } from "@aws-amplify/ui-react";

    export default createTheme({
      name: "studioTheme",
      tokens: {
        space: { value: 12 },
        radii: { value: 4 },
        fontSizes: { base: { value: 16 } }
      }
    });

    const x = 5;
    """
    v = detect_magic_numbers(code, "app.ts", "typescript")
    assert v == []


def test_createTheme_block_multiline_depth_is_skipped_until_closing_brace():
    code = """\
    export default createTheme({
      tokens: {
        components: {
          Button: {
            padding: { value: 8 },
         }
        }
      }
    });

    doThing(10);
    """
    v = detect_magic_numbers(code, "app.ts", "typescript")
    assert _lits(v) == ["10"]


def test_python_dict_key_rows_cols_skips_numbers():
    code = 'description = forms.CharField(widget=forms.Textarea(attrs={"rows":5, "cols":23}))\n'
    v = detect_magic_numbers(code, "app/stream/forms.py", "python")
    assert _lits(v) == []


def test_python_regex_raw_string_numbers_skipped():
    code = "email = re.sub(r'@[A-Za-z]*\\.?[A-Za-z0-9]*', '', email)\n"
    v = detect_magic_numbers(code, "a.py", "python")
    assert v == []


def test_python_numbers_inside_strings_are_removed():
    code = """\
    chrome_options.add_argument("--log-level=3")  # comment
    register_page_test(driver, 'abcdef', 'abcdef@email.com', 'herman1234', "2")
    print("Register Page test end for permission 2")
    """
    v = detect_magic_numbers(code, "a.py", "python")
    assert v == []


def test_numeric_string_object_key_is_not_detected():
    code = '"9": "Sep"'
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert v == []


def test_python_http_status_codes_in_return_responses_are_not_detected():
    code = """\
    return jsonify({'error': 'Missing email'}), 400
    return send_file(video_data, mimetype='video/mp4'), 200
    return json.dumps(available_videos_consolidated), 200
    timeout = 200
    """
    v = detect_magic_numbers(code, "a.py", "python")
    assert _lits(v) == ["200"]


def test_js_regex_after_return_is_skipped():
    code = r'''\
    return /^(\d+):([0-5]\d)$/;
    doThing(10);
    '''
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_jsx_presentation_prop_brace_variants_are_not_detected():
    code = """\
    <Heading level={4}>Title</Heading>
    <Heading level = {4}>Title</Heading>
    doThing(10);
    """
    v = detect_magic_numbers(code, "a.jsx", "javascript")
    assert _lits(v) == ["10"]


def test_js_http_status_in_res_status_call_is_not_detected():
    code = """\
    res.status(500).send('Error during authentication');
    doThing(10);
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_php_html_text_date_is_not_detected():
    code = """\
    <td id="date">2023/09/09</td>
    doThing(10);
    """
    v = detect_magic_numbers(code, "a.php", "php")
    assert _lits(v) == ["10"]


def test_svg_path_fragment_is_skipped_but_normal_code_is_not():
    code = """\
    c-0.9,0.6-1.8,0.9-2.6,0.9
    let x = 5;
    """
    v = detect_magic_numbers(code, "a.tsx", "typescript")
    assert _lits(v) == ["5"]


def test_http_status_in_object_literal_is_not_detected():
    code = """\
    const res = {
        status: 404,
        ok: false
    };
    doThing(10);
    """
    v = detect_magic_numbers(code, "a.js", "javascript")
    assert _lits(v) == ["10"]


def test_rgb_color_values_are_not_detected():
    code = """\
    WHITE = RGBColor(255,255,255)
    LIGHTBLUE = RGBColor(135,206,235)
    x = 10
    """
    v = detect_magic_numbers(code, "a.py", "python")
    assert _lits(v) == ["10"]