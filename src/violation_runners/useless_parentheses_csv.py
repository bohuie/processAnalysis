from __future__ import annotations

import csv

from pathlib import Path
from typing import Iterable, List, Tuple

from src.violation_lists.detect_useless_parentheses import (UselessParenthesesViolation, detect_useless_parentheses_in_code,)

SUPPORTED_EXTS: Tuple[str, ...] = (".js", ".ts", ".java")


def get_csv_columns(fieldnames: List[str]) -> Tuple[str, str, str]:
    pr_id_col = "pr_id" if "pr_id" in fieldnames else ""
    path_col = "file_path" if "file_path" in fieldnames else ""
    code_col = "content" if "content" in fieldnames else ""

    if not path_col:
        for c in ("path", "filename", "file"):
            if c in fieldnames:
                path_col = c
                break

    if not code_col:
        for c in ("file_content", "full_file_content", "full_content", "code", "source", "text"):
            if c in fieldnames:
                code_col = c
                break

    if not pr_id_col:
        raise KeyError(f"Missing pr_id column. Available headers: {fieldnames}")
    if not path_col:
        raise KeyError(f"Missing file_path column. Available headers: {fieldnames}")
    if not code_col:
        raise KeyError(f"Missing content/code column. Available headers: {fieldnames}")

    return pr_id_col, path_col, code_col


def iter_input_rows(reader: csv.DictReader, pr_id_col: str, path_col: str, code_col: str,) -> Iterable[Tuple[int, str, str]]:
    for row in reader:
        pr_raw = (row.get(pr_id_col) or "").strip()
        file_path = (row.get(path_col) or "").strip()

        if not pr_raw or not file_path:
            continue

        if not file_path.lower().endswith(SUPPORTED_EXTS):
            continue

        try:
            pr_id = int(pr_raw)
        except ValueError:
            continue

        yield pr_id, file_path, (row.get(code_col) or "")


def run_from_full_files_csv(in_csv: Path, out_csv: Path, *, debug: bool = False) -> None:
    if not in_csv.exists():
        raise FileNotFoundError(f"CSV not found: {in_csv}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    violations: List[UselessParenthesesViolation] = []
    seen: set[Tuple[int, str, int, int, int, int, str, str]] = set()
    files_scanned = 0

    with in_csv.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row (fieldnames is None).")

        pr_id_col, path_col, code_col = get_csv_columns(list(reader.fieldnames))

        for pr_id, file_path, code in iter_input_rows(reader, pr_id_col, path_col, code_col):
            files_scanned += 1
            try:
                found = detect_useless_parentheses_in_code(code=code, file_path=file_path, pr_id=pr_id)
                for v in found:
                    key = (
                        v.pr_id,
                        v.file_path,
                        v.start_line,
                        v.start_col,
                        v.end_line,
                        v.end_col,
                        v.outer_op,
                        v.inner_op,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    violations.append(v)

            except Exception as e:
                if debug:
                    print(f"[ERROR] {file_path} (pr_id={pr_id}): {type(e).__name__}: {e}")

    with out_csv.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(
            [
                "pr_id",
                "file_path",
                "start_line",
                "start_col",
                "end_line",
                "end_col",
                "outer_op",
                "inner_op",
                "reason",
                "code_snippet",
            ]
        )
        for v in violations:
            w.writerow(
                [
                    v.pr_id,
                    v.file_path,
                    v.start_line,
                    v.start_col,
                    v.end_line,
                    v.end_col,
                    v.outer_op,
                    v.inner_op,
                    v.reason,
                    v.code_snippet,
                ]
            )

    print(f"Scanned files: {files_scanned}")
    print(f"Violations: {len(violations)}")
    print(f"Wrote: {out_csv}")


# ============================================================
# Configurations
# ============================================================
def main() -> None:
    repo_name = "year-long-project-team-15"
    in_csv = Path("data/csv") / repo_name / f"{repo_name}_full_files_at_pr_head.csv"
    out_csv = Path("data/csv") / repo_name / f"{repo_name}_useless_parentheses_violations.csv"
    run_from_full_files_csv(in_csv, out_csv, debug=True)


if __name__ == "__main__":
    main()