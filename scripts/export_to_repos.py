#!/usr/bin/env python3
"""
scripts/export_to_repos.py

Export canonical GitHub data from processAnalysis (PA) into collabAnalysis (CA)
so that CA's LocalDataLoader can serve reports without live GitHub API calls.

PA is the single source of truth. This script reads from PA's data directory and
writes the exact files CA expects into collabAnalysis/data/.

Required canonical inputs (must exist in pa-data/ before running):
  csv/{repo}/{repo}_all_pull_requests.csv
  csv/{repo}/{repo}_PR_commits.csv
  json/{repo}/{repo}_all_pull_requests.json

CA outputs written to ca-data/:
  json/{repo}/{repo}_all_pull_requests.json    (copy from PA json/)
  json/{repo}/{repo}_issues.json               (copy from PA json/, if present)
  json/{repo}/{repo}_commits_by_day.json       (derived from PA csv/PR_commits)
  csv/{repo}/{repo}_PR_commits.csv             (copy from PA csv/)
  csv/{repo}/{repo}_commit_file_changes.csv    (copy from PA csv/, if present)

Usage (from processAnalysis root):
  python scripts/export_to_repos.py
  python scripts/export_to_repos.py --repo-name year-long-project-team-1,team-2
  python scripts/export_to_repos.py --force
  python scripts/export_to_repos.py --pa-data-dir ./data --ca-data-dir ../collabAnalysis/data
"""

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _copy_file(src: Path, dst: Path, force: bool) -> str:
    """Copy src to dst. Returns '[WRITE]' or '[SKIP]'. Creates parent dirs."""
    if dst.exists() and not force:
        return "[SKIP]"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "[WRITE]"


def _derive_commits_by_day(commits_csv: Path, out_path: Path, force: bool) -> str:
    """
    Build {date: {AUTHOR_UPPER: count}} from PR_commits.csv and write JSON.
    Author format matches CommitExtractor.extract_commit_by_day(): uppercase,
    non-alpha characters stripped.
    Returns '[WRITE]', '[SKIP]', or '[ERROR]'.
    """
    if out_path.exists() and not force:
        return "[SKIP]"

    result: dict = {}
    with open(commits_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw_date = (row.get("commit_date") or "")[:10]
            raw_author = (row.get("author") or "").strip()
            if not raw_date or not raw_author:
                continue
            author_key = re.sub(r"[^A-Z\s]", "", raw_author.upper()).strip()
            bucket = result.setdefault(raw_date, {})
            bucket[author_key] = bucket.get(author_key, 0) + 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return "[WRITE]"


# ---------------------------------------------------------------------------
# Per-repo export
# ---------------------------------------------------------------------------

def export_repo(
    repo_name: str,
    pa_data: Path,
    ca_data: Path,
    force: bool,
) -> bool:
    """
    Export one repo. Returns True if all required inputs were present (even if
    some optional files were missing). Returns False if required inputs are absent.
    """
    print(f"\n{'='*70}")
    print(f"[REPO] {repo_name}")
    print(f"{'='*70}")

    failed = False

    # ------------------------------------------------------------------
    # 1. Verify required PA inputs
    # ------------------------------------------------------------------
    required_inputs = [
        pa_data / "csv" / repo_name / f"{repo_name}_all_pull_requests.csv",
        pa_data / "csv" / repo_name / f"{repo_name}_PR_commits.csv",
        pa_data / "json" / repo_name / f"{repo_name}_all_pull_requests.json",
    ]
    for p in required_inputs:
        if not p.exists():
            print(f"  [ERROR] Required input missing: {p}")
            failed = True

    if failed:
        print(f"  [FAIL] Cannot export {repo_name}: missing required inputs above.")
        print(f"         Run unified_github_data_pull.py first.")
        return False

    # ------------------------------------------------------------------
    # 2. Copy required JSON: all_pull_requests.json
    # ------------------------------------------------------------------
    src = pa_data / "json" / repo_name / f"{repo_name}_all_pull_requests.json"
    dst = ca_data / "json" / repo_name / f"{repo_name}_all_pull_requests.json"
    tag = _copy_file(src, dst, force)
    print(f"  {tag} {dst.relative_to(ca_data)}")

    # ------------------------------------------------------------------
    # 3. Copy optional JSON: issues.json
    # ------------------------------------------------------------------
    src = pa_data / "json" / repo_name / f"{repo_name}_issues.json"
    dst = ca_data / "json" / repo_name / f"{repo_name}_issues.json"
    if src.exists():
        tag = _copy_file(src, dst, force)
        print(f"  {tag} {dst.relative_to(ca_data)}")
    else:
        print(f"  [WARN] issues.json not found in PA — CA will fall back to GitHub API for issues")

    # ------------------------------------------------------------------
    # 4. Derive commits_by_day.json from PR_commits.csv
    # ------------------------------------------------------------------
    commits_csv = pa_data / "csv" / repo_name / f"{repo_name}_PR_commits.csv"
    dst = ca_data / "json" / repo_name / f"{repo_name}_commits_by_day.json"
    tag = _derive_commits_by_day(commits_csv, dst, force)
    print(f"  {tag} {dst.relative_to(ca_data)}")

    # ------------------------------------------------------------------
    # 5. Copy required CSV: PR_commits.csv
    # ------------------------------------------------------------------
    src = pa_data / "csv" / repo_name / f"{repo_name}_PR_commits.csv"
    dst = ca_data / "csv" / repo_name / f"{repo_name}_PR_commits.csv"
    tag = _copy_file(src, dst, force)
    print(f"  {tag} {dst.relative_to(ca_data)}")

    # ------------------------------------------------------------------
    # 6. Copy optional CSV: commit_file_changes.csv
    # ------------------------------------------------------------------
    src = pa_data / "csv" / repo_name / f"{repo_name}_commit_file_changes.csv"
    dst = ca_data / "csv" / repo_name / f"{repo_name}_commit_file_changes.csv"
    if src.exists():
        tag = _copy_file(src, dst, force)
        print(f"  {tag} {dst.relative_to(ca_data)}")
    else:
        print(f"  [WARN] commit_file_changes.csv not found in PA — file-change data will be unavailable")

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PA canonical data into CA's data folder"
    )
    parser.add_argument(
        "--repo-name",
        default=None,
        help="Repo name or comma-separated list. If omitted, auto-discover from pa-data/csv/",
    )
    parser.add_argument(
        "--pa-data-dir",
        default=str(PROJECT_ROOT / "data"),
        help="PA canonical data directory (default: ./data)",
    )
    parser.add_argument(
        "--ca-data-dir",
        default=str(PROJECT_ROOT.parent / "collabAnalysis" / "data"),
        help="CA target data directory (default: ../collabAnalysis/data)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing target files",
    )
    args = parser.parse_args()

    pa_data = Path(args.pa_data_dir).resolve()
    ca_data = Path(args.ca_data_dir).resolve()

    print(f"PA data source : {pa_data}")
    print(f"CA data target : {ca_data}")

    # Discover repos
    if args.repo_name:
        repos = [r.strip() for r in args.repo_name.split(",") if r.strip()]
    else:
        csv_root = pa_data / "csv"
        if not csv_root.exists():
            print(f"[ERROR] PA csv directory not found: {csv_root}")
            print("        Run unified_github_data_pull.py first, or pass --pa-data-dir.")
            sys.exit(1)
        repos = sorted(d.name for d in csv_root.iterdir() if d.is_dir())
        if not repos:
            print("[INFO] No repo directories found under pa-data/csv/.")
            print("       Run unified_github_data_pull.py first.")
            sys.exit(0)
        print(f"\nAuto-discovered {len(repos)} repo(s): {', '.join(repos)}")

    failed = []
    for repo in repos:
        ok = export_repo(repo, pa_data, ca_data, args.force)
        if not ok:
            failed.append(repo)

    print(f"\n{'='*70}")
    if failed:
        print(f"[DONE] Completed with failures: {failed}")
        print("       Fix missing inputs and re-run (--force not needed for new files).")
        sys.exit(1)
    print(f"[DONE] Exported {len(repos) - len(failed)}/{len(repos)} repo(s) successfully.")
    print(f"       CA can now serve: pull_requests, commits_by_day, and (if present) issues.")
    print(f"       CA still uses GitHub API for: comments, weekly log.")


if __name__ == "__main__":
    main()
