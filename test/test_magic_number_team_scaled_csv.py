import os
import sys
import csv
import re
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.violations.magic_number_check import (
    MagicNumberConfig,
    detect_magic_numbers_from_code,
    extract_code_from_patch_snippet,
)

DEFAULT_TEAM15_CSV = os.path.join(
    project_root,
    "data",
    "csv",
    "year-long-project-team-15",
    "year-long-project-team-15_commit_file_changes.csv",
)

ENV_PATH = "MAGIC_NUMBER_PATCH_CSV"

# Matches diff hunk headers like: @@ -8,13 +8,36 @@
_HUNK_HEADER_LINE_RE = re.compile(r"^@@\s*-[0-9]+(?:,[0-9]+)?\s*\+[0-9]+(?:,[0-9]+)?\s*@@\s*$", re.MULTILINE)


def _read_patch_snippets(csv_path: str):
    """Yield (row_index, patch_snippet) for each row in the CSV that has a patch_snippet."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "patch_snippet" not in (reader.fieldnames or []):
            raise AssertionError(f"CSV is missing 'patch_snippet' column: {csv_path}")

        for i, row in enumerate(reader, start=1):
            patch = (row.get("patch_snippet") or "").strip()
            # Skip empty patches (GitHub sometimes omits patch for large diffs / binaries)
            if not patch:
                continue
            yield i, patch


def _findings_from_patch(patch: str):
    """Run detection on code extracted from a patch snippet."""
    code = extract_code_from_patch_snippet(patch)
    cfg = MagicNumberConfig(
        ignored_numbers={"0", "1"},
        ignore_in_constant_declarations=False,
        ignore_in_annotations=True,
        treat_negative_as_literal=True,
    )
    return code, detect_magic_numbers_from_code(code, config=cfg)


def test_team_scaled_csv_smoke_and_no_hunk_header_lines_processed():
    """
    Team-scale test (Team 15):
    - Iterate ALL patch_snippet rows from a CSV file
    - Ensure the pipeline does not crash
    - Ensure diff hunk header lines are removed by extract_code_from_patch_snippet()
      so we never treat @@ -a,b +c,d @@ as code.

    Run:
      MAGIC_NUMBER_PATCH_CSV=data/csv/year-long-project-team-15/year-long-project-team-15_commit_file_changes.csv \
      pytest -q test/test_magic_number_team_scaled_csv.py
    """
    csv_path = os.environ.get(ENV_PATH, DEFAULT_TEAM15_CSV)
    assert os.path.exists(csv_path), f"CSV file not found: {csv_path}"

    checked = 0

    for row_idx, patch in _read_patch_snippets(csv_path):
        checked += 1

        # sanity: patch should have (optional) hunk headers, but extracted code should not
        code, findings = _findings_from_patch(patch)

        # Invariant A: extracted code should not contain any full hunk header line.
        # Check line-by-line so strings containing '@@' (like '@@toPrimitive') won't fail.
        for line in code.splitlines():
            assert not _HUNK_HEADER_LINE_RE.match(line.strip()), (
                f"Row {row_idx}: extract_code_from_patch_snippet leaked a hunk header line into code. "
                f"Line={line!r}"
            )

        # Invariant B: even if the detector flags real numeric literals, it should never
        # flag something *on a hunk header line*.
        for f in findings:
            assert not f.line_text.strip().startswith("@@"), (
                f"Row {row_idx}: detector produced a finding on a hunk header line. "
                f"Literal={f.literal}, line={f.line_text!r}"
            )

    assert checked > 0, f"No non-empty patch_snippet rows found in {csv_path}"


