# What is Magic Number?
Magic Number is a hard-coded/unexplained numerical literal embedded within code logic rather than being represented by a named constant.

Example:
```bash
if (strlen(pw) > 7)
```
We may ask "What does 7 mean?", which indicates a *code smell* characteristic. For this type of code smell, we classify this
as **Magic Number** (Positive case) because the code has a hard-coded numeric literal embedded in logic without an explanatory named constant (unexplained numerical).

What fixes it:
```bash
const MAX_PASSWORD_LENGTH = 7;
if (len > MAX_PASSWORD_LENGTH) ...
```
The number is not magic anymore, since it has a descriptive name, centralized (change in one place), and less likely to be inconsistently duplicated -> explained numerical. Furthermore, the value stay the same while the program runs.

## Magic Number Detection Module
This module implements an explanation about Magic Number detection system for analyzing real-world repository data.
It consist of four main files:

## 1) `rules.py`
Defines the rule registry for Magic Number detection.

**Type of Contexts**:
    - `CALL_ARGS`: When a numeric literal used as a function or method argument.
        e.g. x = request.get(url, 10)
    - `THRESHOLD`: When a numeric literal used in a comparison expression (>, <, >=, <=, ==, !=).
        e.g. if (strlen(pw) > 7)
    - `LOOP BOUND`: When a numeric literal used to control loop iteration bounds.
        e.g. for i in range(12) 
    - `ASSIGNMENT`: When a numeric literal assigned directly to a variable.
        e.g. timeout = 10
    - `GENRIC`: When a numeric literal detected outside known safe cases and not classified into a more specific context

## 2) `detect_magic_numbers.py`
Implements the Magic Number detection engine.

### What it does
- Detects numeric literals in source code.
- Detects the condition:
    - Constant definitions: const, final, constexpr, let, val, static final, #define → name → literal,
      define( + string name + , + literal + ), ALL_CAPS_CONST_DEF_RE (Capitalized constant)
    - Safe literals (0, 1)
    - Named constants (math.pi, Math.pi, MATH.PI)
If the numeric literal NOT MATCH any of these -> MAGIC NUMBER
- Classifies literals into contexts: `CALL_ARG`, `THRESHOLD`, `LOOP_BOUND`, `ASSIGNMENT`, `GENERIC`

## 3) `test_detect_magic_numbers_unit.py`
Unit tests for the detection logic.

### How to Run
```bash
 pytest -q test/test_detect_magic_numbers_unit.py
```

## 4) `test_detect_magic_numbers.py`
Runs Magic Number detection on full repository file contents.

### How to Run
```bash
 python test/test_detect_magic_numbers.py
```
⚠️ Before running, open [test/test_detect_magic_numbers.py](test/test_detect_magic_numbers.py) and set:
- `REPO_NAME` (string)

## Architecture Diagram

                ┌─────────────────────────────────────────────┐
                │  Full file contents CSV                     │
                │  *_full_files_at_pr_head.csv                │
                └───────────────────────────┬─────────────────┘
                                            │
                                            ▼
┌──────────────────────────────┐   calls   ┌──────────────────────────────┐
│ test/test_detect_magic_      ├──────────►│ src/violations/detect_magic_ │ 
| numbers.py                   |           | numbers.py                   |
│ (repo-scale runner)          │           │                              │
│ - read rows                  │           │ - scan numeric literals      │
│ - run detector per file      │           │ - exclude constants / safe   │
│ - write violations CSV       │           │ - classify context           │
└───────────────┬──────────────┘           └───────────────┬──────────────┘
                │                                          │
                │ validates rule_ids via                   │ uses rule registry
                ▼                                          ▼
┌──────────────────────────────┐           ┌──────────────────────────────┐
│ test/test_detect_magic_      │           │ src/violations/rules.py      │
│ numbers_unit.py              │           │ - rule IDs (context_type)    │
│ (unit tests)                 │           │ - descriptions + rationale   │
└──────────────────────────────┘           └──────────────────────────────┘

Output:
  *_magic_number_violations.csv

## File Location Diagram
processAnalysis/
│
├── documentation/
│   └── detect_magic_numbers.md
│
├── src/
│   └── violations/
│       ├── __init__.py
│       ├── rules.py
│       └── detect_magic_numbers.py
│
├── test/
│   ├── test_detect_magic_numbers_unit.py
│   └── test_detect_magic_numbers.py
│
└── data/
    └── csv/
        └── year-long-project-team-*/
            ├── year-long-project-team-*_full_files_at_pr_head.csv
            └── year-long-project-team-*_magic_number_violations.csv
