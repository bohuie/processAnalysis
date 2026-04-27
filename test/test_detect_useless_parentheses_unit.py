from src.violation_lists.detect_useless_parentheses import detect_useless_parentheses_in_code

def test_flags_a_plus_paren_b_times_c():
    code = "const x = a + (b * c);"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=1)

    assert len(v) == 1
    assert v[0].outer_op == "+"
    assert v[0].inner_op == "*"


def test_flags_paren_a_times_b_plus_c():
    code = "const x = (a * b) + c;"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=2)

    assert len(v) == 1
    assert v[0].outer_op == "+"
    assert v[0].inner_op == "*"


def test_does_not_flag_a_times_paren_b_plus_c():
    code = "const x = a * (b + c);"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=3)

    assert len(v) == 0


def test_does_not_flag_when_parent_not_binary_expression():
    code = "if ((b * c)) { console.log('ok'); }"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=4)

    assert len(v) == 0

def test_java_flags_redundant_parentheses():
    code = "int x = a + (b * c);"
    v = detect_useless_parentheses_in_code(code=code, file_path="X.java", pr_id=5)

    assert len(v) == 1
    assert v[0].outer_op == "+"
    assert v[0].inner_op == "*"

def test_jsx_file_is_ignored_due_to_scope():
    code = "const X = () => ( <Video /> );"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.jsx", pr_id=6)

    assert len(v) == 0

def test_unsupported_language_returns_empty_list():
    code = "x = a + (b * c)"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.py", pr_id=7)

    assert isinstance(v, list)
    assert len(v) == 0

def test_does_not_flag_associativity():
    code = "const x = a + (b + c);"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=8)

    assert isinstance(v, list)
    assert len(v) == 0

def test_does_not_flag_unknown_operator():
    code = "const x = a ?? (b ?? c);"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=9)

    assert isinstance(v, list)
    assert len(v) == 0

def test_two_parenthesized_binary_expressions_equal_precedence():
    code = "const x = (a + b) + (c + d);"
    v = detect_useless_parentheses_in_code(code=code, file_path="x.js", pr_id=11)

    assert len(v) == 0
