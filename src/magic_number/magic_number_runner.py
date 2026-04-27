'''
Magic Number Team Repository Runner

This script runs the magic number detector on file snapshots extracted
from pull request (PR) head commits by the full-file enrichment pipeline.

Purpose: How code quality evolves across PRs

Input:
  data/csv/<REPO_NAME>/<REPO_NAME>_full_files_at_pr_head.csv
Required columns:
  pr_id, head_sha, file_path, content

Output:
  data/csv/<REPO_NAME>/<REPO_NAME>_magic_number_violations.csv
Columns:
   pr_id, head_sha, file_path, line, literal, line_text

'''

import csv
import sys
from pathlib import Path

from src.magic_number.detect_magic_number import detect_magic_numbers

# Change this to run a different repo dataset
REPO_NAME = "year-long-project-team-15"

IN_CSV = Path("data/csv") / REPO_NAME / f"{REPO_NAME}_full_files_at_pr_head.csv"
OUT_CSV = Path("data/csv") / REPO_NAME / f"{REPO_NAME}_magic_number_violations.csv"


def _set_csv_field_limit():
    """
    Some file contents can be huge.
    This increases the CSV field limit so DictReader does not crash.
    """
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)


def main():
    _set_csv_field_limit()

    if not IN_CSV.exists():
        raise FileNotFoundError(f"Input CSV not found: {IN_CSV}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    out_rows = []
    scanned = 0
    skipped_missing = 0

    with IN_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # Quick validation
        required = {"pr_id", "head_sha", "file_path", "content"}
        if reader.fieldnames is None:
            raise ValueError("Input CSV missing header row.")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Input CSV missing required columns: {sorted(missing)}")

        for row in reader:
            pr_id = (row.get("pr_id") or "").strip()
            head_sha = (row.get("head_sha") or "").strip()
            file_path = (row.get("file_path") or "").strip()
            content = row.get("content") or ""

            if not file_path or not content:
                skipped_missing += 1
                continue

            scanned += 1

            violations = detect_magic_numbers(
                code=content,
                file_path=file_path,
                language="auto",
            )

            for v in violations:
                out_rows.append({
                    "pr_id": pr_id,
                    "head_sha": head_sha,
                    "file_path": file_path,
                    "line": v["line"],
                    "literal": v["literal"],
                    "line_text": v.get("line_text", ""),
                })

            # Light progress indicator
            if scanned % 5000 == 0:
                print(f"... scanned {scanned} file-snapshots, collected {len(out_rows)} violations")

    fieldnames = ["pr_id", "head_sha", "file_path", "line", "literal", "line_text"]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"✅ Scanned {scanned} file-snapshots (skipped {skipped_missing} empty).")
    print(f"✅ Wrote {len(out_rows)} violations → {OUT_CSV}")


if __name__ == "__main__":
    main()