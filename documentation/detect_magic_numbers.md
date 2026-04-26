# What is a magic number?
A **magic number** is a numeric literal that is hard-coded directly in program logic instead of being defined as a named constant.

Hard-coding parameters can make code harder to understand and maintain, because it becomes difficult to identify the meaning of the value or update it consistently during debugging.

Example:
```bash
if (len(password) > 7)
```
In this case, it is unclear what the value 7 represents.
Because the number is embedded directly in the logic without explanation, it is considered a **magic number**.

Better Practice:
```bash
const MAX_PASSWORD_LENGTH = 7;
if (len(password) > MAX_PASSWORD_LENGTH)
```

---

## Magic Number Detection Module
This module implements a static analysis detector for identifying magic numbers in repository code.

The detector operates on **full-file snapshots** extracted from the head commits of pull requests (PRs) and scans each file for numeric literals embedded in program logic. This approach allows the detector to analyze the full content of a file, rather than only the small code fragments shown in diffs.

**NOTE**: A full-file snapshot refers to the complete content of a file at the head commit of a PR, whereas a diff shows only the lines that changed between two commits.

The system applies context-aware filtering to exclude numbers appearing in non-logical contexts such as comments, strings, styling blocks, or markup.

The implementation is located in:

```bash
src/magic_number/
```

### Pipeline
```bash
PR Head Commit
      ↓
Full-file Snapshot
      ↓
File Context Cleaning
      ↓
Numeric Literal Detection
      ↓
Contextual Filtering
      ↓
Magic Number Violations
```


### Scope

This detector identifies numeric literals embedded in **program logic** that represent magic numbers, focusing on numbers that influence program behavior rather than **presentation or formatting values**.

 The detector analyzes full-file snapshots from PR head commits and scans code line-by-line after removing non-logical contexts such as comments, strings, regex patterns, styling blocks, and markup content. Numbers used for presentation, formatting, protocol standards, or data structure keys are intentionally ignored to reduce false positives. 


### Limitations

The detector relies on pattern-based heuristics and contextual filtering.
As a result, some edge cases may still produce false positives or false negatives.

For example:
- New styling frameworks may introduce patterns not yet included in the filter rules.
- Numeric literals embedded in complex expressions may require deeper semantic analysis.

If new styling patterns appear in future frameworks, they may need to be added to the pattern configuration to maintain detection accuracy.


### Repository Analysis Pipeline
The detector runs as part of a repository scale analysis pipeline.

```bash
scripts/enrich_full_files.py
        │
        ▼
*_full_files_at_pr_head.csv
        │
        ▼
src/magic_number/magic_number_runner.py
        │
        ▼
src/magic_number/detect_magic_number.py
        │
        ▼
src/magic_number/magic_number_filter.py
        │
        ▼
*_magic_number_violations.csv
```

---

# How Detection Works
The detection process is implemented primarily in:

```bash
detect_magic_number.py
magic_number_filter.py
magic_number_patterns.py
```


## Detection Pipeline
```bash
original_line
    │
    ▼
remove_block_comments()
    │
    ▼
remove_regex_literals()
    │
    ▼
remove_strings()
    │
    ▼
remove_single_line_comment()
    │
    ▼
update_style_block_state()
    │
    ├── if inside presentation/style block → Skip line
    ▼
is_pure_constant_definition()
    │
    ▼
check non-logic content
(HTML text / SVG vector)
    │
    ├── if matched → Skip line
    ▼
NUMERIC_RE.finditer()
    │
    ▼
apply numeric filters:
    - SAFE_LITERALS
    - HTTP status contexts
    - RGB color context
    - Object key numbers
    - Constant RHS literal
    - CSS units
    - Presentation call context
    - JSX presentation props
    - Style/presentation keyword context
    │
    ▼
remaining numbers
    │
    ▼
emit magic number violation
```


The workflow proceeds as follows:

## 1) Language Identification
The programming language of a file is inferred from its extension using
the `EXT_TO_LANG` mapping defined in 

```bash
magic_number_patterns.py.
```

Files with unsupported extensions are classified as **generic**
and skipped during analysis (e.g., .md).


## 2) File Filtering
`should_skip_file()` filters out files that are:
- **Formatting files**: Style sheets or other formatting-related assets
- **Style folders**: Directories used for UI styling or theming
- **Third-party or generated code**: Code not directly written or maintained by developers (e.g., vendor libraries, generated artifacts, docs/tests)
- **Minified files**: Compressed CSS or HTML files with removed whitespace and shortened identifiers


## 3) Context Cleaning
Before detecting numbers, the detector removes non-logical content from each line.

The following functions from `magic_number_filter.py` perform this preprocessing:

```bash
remove_block_comments()
remove_strings()
remove_regex_literals()
remove_single_line_comment()
```

These functions ensure that numeric literals appearing inside comments, strings, or regular expressions are removed/ignored.


## 4) Presentation Context Detection
Some numeric literals appear in **styling or UI configuration**, which are not considered part of program logic.

The function `update_style_block_state()` tracks styling or presentation blocks.
When the detector enters such a block, numeric literals inside it are ignored to avoid false positives.

Example:
```bash
<Button
  sx={{
    marginTop: 8,
    padding: 12
  }}
/>
```
In this case, `8` and `12` represent visual layout values, not logical program parameters. Therefore they are skipped by the detector.

### Additional checks filter out:
Additional checks remove numeric literals used in common styling contexts.

- CSS unit values: (e.g.,`width: 100px;` , `margin: 8rem;` , `opacity: 0.5;`)
- Presentation component properties: (e.g.,`<CircularProgress size={24} />`)
- Styling keywords: (e.g., `marginRight`, `fontWeight` )


## 5) Numeric Literal Detection
After preprocessing, the detector scans the remaining code using the numeric literal pattern defined in:
Example:

```bash
NUMERIC_RE
```

in `magic_number_patterns.py`.
Each numeric literal match is then evaluated using **contextual filters**.


## 6) Contextual Filtering
Several filtering functions remove numeric literals that are unlikely to represent Magic Numbers, including:

```bash
is_http_status_context()
is_object_key_number()
is_rgb_color_context()
has_css_unit_after_number()
is_style_context()
```

These checks eliminate common false positives such as:
- HTTP constant numbers (response codes)
- Object keys: Numeric literals that appear as keys in objects or dictionaries.
Example:
```bash
const statusMessages = {
  404: "Not Found",
  500: "Server Error"
};
```
- RGB color values
- CSS dimension values


## 7) Reporting Violations
Numeric literals that remain after filtering are recorded as Magic Number violations.

Each violation record contains:

```bash
file
line
literal
line_text
```

These results are written to a CSV file for further analysis.

---

# Architecture Diagram
```bash

                ┌──────────────────────────────┐
                │ GitHub PR history            │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ enrich_full_files.py         │
                │ - Fetch PR head snapshots    │
                │ - Build full-file CSV        │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ *_full_files_at_pr_head.csv  │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ magic_number_runner.py       │
                │ - Load CSV rows              │
                │ - Run detector per file      │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌──────────────────────────────┐
                │ detect_magic_number.py       │
                │ - Infer language             │
                │ - Scan numeric literals      │
                │ - Apply detection pipeline   │
                └──────────────┬───────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ magic_number_filter.py       │  │ magic_number_patterns.py     │
│ - Remove comments/strings    │  │ - Regex patterns             │
│ - Skip presentation blocks   │  │ - Language mapping           │
│ - Filter false positives     │  │ - Safe literals/keywords     │
└──────────────┬───────────────┘  └──────────────┬───────────────┘
               └──────────────┬──────────────────┘
                              ▼
                ┌──────────────────────────────┐
                │ *_magic_number_violations.csv│
                │ - file                       │
                │ - line                       │
                │ - literal                    │
                │ - line_text                  │
                └──────────────────────────────┘
```


## Architecture Summary
```bash

 GitHub PR History
        │
        ▼
 enrich_full_files.py
 (Extract full file content
  at each PR head commit)
        │
        ▼
 *_full_files_at_pr_head.csv
        │
        ▼
 magic_number_runner.py
 (Reads each file snapshot
  from the CSV dataset)
        │
        ▼
 detect_magic_number.py
 (Main detection pipeline)
        │
        ▼
 magic_number_filter.py
 (Removes false positives:
  comments, strings, regex,
  styling, HTML/SVG, etc.)
        │
        ▼
 magic_number_patterns.py
 (Shared language mappings,
  regex patterns, safe literals,
  keyword sets, block openers)
        │
        ▼
 *_magic_number_violations.csv
 (Final output of detected
  magic number violations)
```

---

# File Structure

```bash
processAnalysis/
│
├── documentation/
│   └── detect_magic_numbers.md
│
├── src/
│   └── magic_number/
│       ├── detect_magic_number.py
│       ├── magic_number_filter.py
│       ├── magic_number_patterns.py
│       └── magic_number_runner.py
│
├── test/
│   └── test_magic_number_unit.py
│
└── data/
    └── csv/
        └── <repository-name>/
            ├── *_full_files_at_pr_head.csv
            └── *_magic_number_violations.csv
```