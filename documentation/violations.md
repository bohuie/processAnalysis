# Violations Detection Plan

This document describes how violation detection is designed, implemented, and tested in this repository.

---

## What is a “Violation”?

In this project, a violation is a detectable pattern in source code that may indicate:
- Maintainability issues
- Code smells
- Deviations from recommended coding practices

Each violation is implemented as a **detector** with:
- Clear and testable behavior
- Controlled unit tests using synthetic data
- The ability to scale to real project data

---

## Repository Setup
This violation detector assumes:

- The repository environment is already set up according to the `README.md`
- Python virtual environment is activated
- Dependencies for testing (`pytest`) are installed

No additional setup is required beyond the existing project environment.

---

## MagicNumberCheck 

**What is a Magic Number?**
A magic number is a numeric literal used directly in code without contextual explanation.

Example:

```bash
setTimeout(runTask, 3000);
```

Preferred alternative:

```bash
const TIMEOUT_MS = 3000;
setTimeout(runTask, TIMEOUT_MS);
```

Using named constants improves readability, maintainability, and intent clarity.

**Design Goals:**
- **Simple and testable** (heuristic-based and no AST parsing yet)
- **Language-agnostic where possible** (works across mixed-language repositories)
- **Safe to run on real project data** (patch snippets)
- **Easy to extend later in later iteration**s (e.g., AST-based or language-specific parsing)

**What it Detects:**
- Integer literals (e.g., `24`), 
- Floating-point literals (e.g., `1.05`), 
- Scientific notation (e.g., `1e10`)
- Negative literals (configurable)

**What it Ignores by Default:**
To reduce false positives, the detector ignores:
- Trivial numbers (`0`, `1`)
- Java-style constant declarations (e.g., `static final`)
- Annotation lines (e.g., `@Size(10)`)
- Numbers embedded in identifiers (e.g., `var1`, `HTTP2`)
- GitHub diff hunk headers (`@@ -11,15 +11,17 @@`)

These behaviors are configurable via `MagicNumberConfig`.

---

## How to Run
All violation detectors must follow this testing progression:

### 1. Controlled Unit Tests

**Purpose**
- Validate detection logic using small and made-up code snippets
- Ensure behavior is deterministic and verifiable
- Isolate detector logic from repository data and I/O

**Run**
```bash
pytest -q test/test_magic_number_check.py
```

**Expected output (example):** 
..........                                          [100%]
... passed in ...s

### 2. Team-Scale Tests using a Patch Snippet (Team 15)

**Purpose**
- Validate behavior on real GitHub diff data (`patch_snippet`)
- Ensure diff metadata is handled correctly
- Demonstrate feasibility before scaling to all teams

**Key Insight**
GitHub patch snippets include numeric values in diff headers (e.g., `@@ -11,15 +11,17 @@`). These must not be interpreted as magic numbers.

**Run**
```bash
pytest -q test/test_magic_number_team15_patch_fixture.py
```

**Expected output (example):** 
..........                                          [100%]
... passed in ...s

### 3. Full `patch_snippet` Team-Scale Test 
After running your target repositories (added in the repository list) following the steps in README.md, you should obtain a CSV file in the following format: 

```
data/
└── csv/
    └── year-long-project-team-<team number>/
        └── year-long-project-team-<team number>_commit_file_changes.csv
```

This CSV contains the `patch_snippet` data required for the full team-scale magic number detection test.

**Run**
```bash
MAGIC_NUMBER_PATCH_CSV=data/csv/year-long-project-team-<team number>/year-long-project-team-<team number>_commit_file_changes.csv \
pytest -q test/test_magic_number_team_scaled_csv.py
```

Example (Team 15):
```bash
MAGIC_NUMBER_PATCH_CSV=data/csv/year-long-project-team-15/year-long-project-team-15_commit_file_changes.csv \
pytest -q test/test_magic_number_team_scaled_csv.py
```

**Expected output (example):** 
..........                                          [100%]
... passed in ...s

This test is a unit test. It ensures that the detector does not crash on real GitHub diff data, diff hunk headers `(@@ -36,18 +59,6 @@)` are never misclassified, the detector is safe to scale, and the logic works across all team patches (e.g., team 15).

**Notes on Test Configuration**
This test is configurable via an environment variable:

- `ENV_PATH = "MAGIC_NUMBER_PATCH_CSV"` (already defined in the test)
- Setting `MAGIC_NUMBER_PATCH_CSV` allows the test to run against **any team’s CSV file** without modifying the test code

The test file also includes a default fallback path **(DO NOT EDIT)**:

```bash
DEFAULT_TEAM15_CSV = os.path.join(
    project_root,
    "data", "csv",
    "year-long-project-team-15",
    "year-long-project-team-15_commit_file_changes.csv",
)

ENV_PATH = "MAGIC_NUMBER_PATCH_CSV"
```
Keep this default as a fallback.

**To test another team, simply override it using the `MAGIC_NUMBER_PATCH_CSV` environment variable as shown above.**

### 4. (Future) All-Team Scaling

Planned next steps once detectors are validated at the team level:

- Apply the same violation detectors across all teams’ patch-level CSV data
- Aggregate violation counts per team, repository, or time window
- Integrate aggregated metrics with downstream analysis and visualization pipelines

This staged approach ensures detector correctness and robustness before full cross-team deployment.

---

## Extending Violations
To add a new violation detector:
- Create a detector under:

```bash
 src/violations/
```

- Write controlled unit tests using synthetic examples
- Add at least one Team-scale patch test
- Document assumptions and limitations

---

## Code and Test Locations
src/
└── violations/
    ├── __init__.py
    └── magic_number_check.py
test/
├── test_magic_number_check.py                      # Synthetic data
├── test_magic_number_team15_patch_fixture.py       # Team 15 a patch data test
└── test_magic_number_team_scaled_csv.py            # All patch data test per team

---

## Pipeline Flow

Violation detection is designed as a lightweight, modular layer that operates on existing repository data rather than replacing the core analysis pipeline.

At a high level, the flow is:

GitHub API  
↓  
patch_snippet (from file change data)  
↓  
Violation Detectors (e.g., MagicNumberCheck)  
↓  
Aggregated Violation Metrics  
↓  
Analysis / Graphs (future integration)

**Key points:**
- Violations consume extracted diff data (`patch_snippet`) generated by the existing pipeline.
- Detectors run independently from PR communication and branching analysis.
- This design allows violations to be added incrementally without disrupting current workflows.

---

## Input Data for Violation Detection
Violation detectors operate on GitHub patch snippets, which represent the line-level code changes introduced by each commit.

For Team-level and full-scale analysis, violation detection uses the following dataset:

```bash
data/csv/year-long-project-team-<team>/year-long-project-team-<team>_commit_file_changes.csv
```

**Why _commit_file_changes.csv file is used:**

- Each row represents a single file change within a specific commit
- The `patch_snippet` column contains the raw GitHub diff, which is the primary input for code-level violation detection
- The dataset preserves commit context (`commit_sha`) and PR context (`pr_id`)
- File-level granularity allows violations to be traced back to exact files and aggregated per commit, PR, or team in later analysis stages

This design ensures that violation detection:
- Does not require access to the full repository source tree
- Can be applied consistently across different programming languages
- Remains reproducible and safe to run on historical data

Other CSV outputs (e.g., PR metadata, review comments, or cleaned summary tables) are not used directly for violation detection, as they do not contain line-level code diffs.

---

