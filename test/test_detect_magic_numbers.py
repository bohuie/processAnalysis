"""
Team-15 full-file Magic Number detection.

Reads:
  data/csv/year-long-project-team-15/year-long-project-team-15_full_files_at_pr_head.csv

Writes:
  data/csv/year-long-project-team-15/year-long-project-team-15_magic_number_violations.csv

Run:
  python test/test_detect_magic_numbers.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from itertools import chain
from typing import Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.violations.detect_magic_numbers import detect_magic_numbers, MagicNumberViolation

REPO_NAME = "year-long-project-team-15"
IN_CSV = Path("data/csv") / REPO_NAME / f"{REPO_NAME}_full_files_at_pr_head.csv"
OUT_CSV = Path("data/csv") / REPO_NAME / f"{REPO_NAME}_magic_number_violations.csv"

def _pick_column(fieldnames: List[str], candidates: List[str]) -> Optional[str]:
    lower_map = {f.lower(): f for f in fieldnames}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None

def resolve_columns(fieldnames: List[str]) -> Tuple[str, str, str, str]:
    pr_id_col = _pick_column(fieldnames, ["pr_id", "pull_request_id", "pr", "pull_request_number", "number"])
    sha_col = _pick_column(fieldnames, ["head_sha", "sha", "commit_sha", "headCommitSha", "head"])
    path_col = _pick_column(fieldnames, ["file_path", "path", "filename", "file", "repo_path"])
    content_col = _pick_column(fieldnames, ["content", "file_content", "full_content", "text", "source", "code"])

    missing = [name for name, col in [
        ("pr_id", pr_id_col),
        ("head_sha", sha_col),
        ("file_path", path_col),
        ("content", content_col),
    ] if col is None]

    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {fieldnames}")

    return pr_id_col, sha_col, path_col, content_col


# Optional
EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
}


def infer_language(file_path: str) -> str:
    return EXT_TO_LANG.get(Path(file_path).suffix.lower(), "generic")


# Row -> list[violations]
def violations_from_row(row: Dict[str, str], pr_id_col: str, sha_col: str, path_col: str, content_col: str):
    file_path = row.get(path_col) or ""
    content = row.get(content_col) or ""
    if not file_path or not content:
        return []

    pr_id_raw = (row.get(pr_id_col) or "").strip()
    head_sha = (row.get(sha_col) or "").strip()

    try:
        pr_id = int(pr_id_raw) if pr_id_raw.isdigit() else 0
    except Exception:
        pr_id = 0

    vlist = detect_magic_numbers(content, language=infer_language(file_path))

    # Rewrite metadata from <inline> -> Real PR/file context
    return [
        MagicNumberViolation(
            pr_id=pr_id,
            head_sha=head_sha,
            file_path=file_path,
            line=v.line,
            col=v.col,
            literal=v.literal,
            context_type=v.context_type,
            snippet=v.snippet,
        )
        for v in vlist
    ]


def main():
    if not IN_CSV.exists():
        raise FileNotFoundError(f"Input CSV not found: {IN_CSV}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with IN_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Input CSV missing header row.")

        pr_id_col, sha_col, path_col, content_col = resolve_columns(reader.fieldnames)

        # Map each row -> list[violations]
        # Flatten all lists into one stream
        all_violations = list(
            chain.from_iterable(
                map(lambda r: violations_from_row(r, pr_id_col, sha_col, path_col, content_col), reader)
            )
        )

    # Write output
    fieldnames = ["pr_id", "head_sha", "file_path", "line", "col", "literal", "context_type", "snippet"]

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
        w = csv.DictWriter(f_out, fieldnames=fieldnames)
        w.writeheader()
        # Single loop for writing
        for v in all_violations:
            w.writerow(v.to_dict())

    print(f"✅ Wrote {len(all_violations)} violations → {OUT_CSV}")


if __name__ == "__main__":
    main()

