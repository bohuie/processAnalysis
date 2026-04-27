#!/usr/bin/env python3
"""
scripts/unified_github_data_pull.py

Pull ALL GitHub data once per repo and write the canonical dataset consumed by
both processAnalysis (PA) and collabAnalysis (CA).

Canonical outputs (relative to --output-dir, default ./data):
  PA (already expected by analysis.py and event_labelling):
    csv/{repo}/{repo}_all_pull_requests.csv
    csv/{repo}/{repo}_PR_commits.csv
    csv/{repo}/{repo}_commit_file_changes.csv
    csv/{repo}/{repo}_review-comments.csv
  CA (read by CA LocalDataLoader):
    json/{repo}/{repo}_all_pull_requests.json   <- PullRequest reconstruction
    json/{repo}/{repo}_issues.json              <- Issue reconstruction
    json/{repo}/{repo}_commits_by_day.json      <- commits_by_day dict (derived from PR commits)

Notes:
  - commits_by_day is derived from PR-linked commits (not repo-wide commits).
    This is a close approximation for course repos where nearly all work is via PRs.
  - Log (CA weekly log) is not extracted here — it reads a git branch and is CA-specific.
  - Comments are not cached for CA — CA's Comment model requires live anonymization context.

Usage (from processAnalysis root):
  python scripts/unified_github_data_pull.py \
      --repo-owner COSC-499-W2023 \
      --repo-name year-long-project-team-1 [,team-2,...]
      [--output-dir ./data] [--force]
      [--no-issues] [--no-commits] [--no-files] [--no-comments]

Requires: GITHUB_TOKEN in env or .env file.
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(verbose=False)

from scripts.app import extract_repository_data
from src.extractors.pull_request_extractor import PullRequestExtractor


# ---------------------------------------------------------------------------
# Skip / existence checks
# ---------------------------------------------------------------------------

def _pa_files_exist(output_dir: Path, repo_name: str) -> bool:
    """True when the minimum PA CSV files already exist."""
    csv_dir = output_dir / "csv" / repo_name
    required = [
        csv_dir / f"{repo_name}_all_pull_requests.csv",
        csv_dir / f"{repo_name}_PR_commits.csv",
    ]
    return all(p.exists() for p in required)


def _pr_json_exists(output_dir: Path, repo_name: str) -> bool:
    return (
        output_dir / "json" / repo_name / f"{repo_name}_all_pull_requests.json"
    ).exists()


def _issues_json_exists(output_dir: Path, repo_name: str) -> bool:
    return (
        output_dir / "json" / repo_name / f"{repo_name}_issues.json"
    ).exists()


def _commits_by_day_exists(output_dir: Path, repo_name: str) -> bool:
    return (
        output_dir / "json" / repo_name / f"{repo_name}_commits_by_day.json"
    ).exists()


# ---------------------------------------------------------------------------
# Issue extraction
# ---------------------------------------------------------------------------

def extract_and_save_issues(
    extractor: PullRequestExtractor,
    output_dir: Path,
    repo_name: str,
    force: bool,
) -> None:
    """
    Fetch all issues (excl. PRs) via GitHub API and save as raw JSON.
    CA reconstructs Issue model objects directly from this JSON.
    """
    out_path = output_dir / "json" / repo_name / f"{repo_name}_issues.json"

    if not force and out_path.exists():
        print(f"[SKIP] Issues already exist: {out_path.name}")
        return

    print("[INFO] Fetching issues from GitHub API...")
    url = (
        f"https://api.github.com/repos/{extractor.repo_owner}"
        f"/{extractor.repo_name}/issues?state=all&per_page=100"
    )

    all_issues = []
    page = 1
    while url:
        resp = extractor.make_request_with_backoff(url)
        batch = resp.json()
        if not batch:
            break
        all_issues.extend(batch)
        url = resp.links.get("next", {}).get("url")
        print(f"[INFO]   Issues page {page}: {len(batch)} items, total so far: {len(all_issues)}")
        page += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_issues, f, indent=2, default=str)
    print(f"[INFO] Issues saved ({len(all_issues)} items) → {out_path}")


# ---------------------------------------------------------------------------
# commits_by_day derivation
# ---------------------------------------------------------------------------

def derive_commits_by_day(
    output_dir: Path,
    repo_name: str,
    force: bool,
) -> None:
    """
    Build {date: {AUTHOR_UPPER: count}} from PR_commits.csv and save as JSON.
    CA's LocalDataLoader reads this to populate commits_by_day without API calls.

    Author format matches CommitExtractor.extract_commit_by_day():
      uppercase, non-alpha characters stripped.
    """
    out_path = output_dir / "json" / repo_name / f"{repo_name}_commits_by_day.json"

    if not force and out_path.exists():
        print(f"[SKIP] commits_by_day already exists: {out_path.name}")
        return

    commits_csv = output_dir / "csv" / repo_name / f"{repo_name}_PR_commits.csv"
    if not commits_csv.exists():
        print(f"[WARN] PR_commits.csv not found; skipping commits_by_day derivation")
        return

    print("[INFO] Deriving commits_by_day from PR_commits.csv...")
    result: dict = {}

    with open(commits_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw_date = (row.get("commit_date") or "")[:10]    # "YYYY-MM-DD"
            raw_author = (row.get("author") or "").strip()
            if not raw_date or not raw_author:
                continue
            author_key = re.sub(r"[^A-Z\s]", "", raw_author.upper()).strip()
            bucket = result.setdefault(raw_date, {})
            bucket[author_key] = bucket.get(author_key, 0) + 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    total_days = len(result)
    total_commits = sum(sum(v.values()) for v in result.values())
    print(f"[INFO] commits_by_day: {total_days} days, {total_commits} commit entries → {out_path}")


# ---------------------------------------------------------------------------
# Per-repo extraction
# ---------------------------------------------------------------------------

def extract_one(
    *,
    repo_owner: str,
    repo_name: str,
    output_dir: Path,
    force: bool,
    include_commits: bool,
    include_files: bool,
    include_comments: bool,
    include_issues: bool,
) -> bool:
    """
    Extract one repository. Returns True on success (or skip), False on failure.
    """
    print(f"\n{'='*70}")
    print(f"[REPO] {repo_owner}/{repo_name}")
    print(f"{'='*70}")

    # --- PA extraction (PRs, commits, file changes, comments) ---
    pa_done = _pa_files_exist(output_dir, repo_name)
    pr_json_done = _pr_json_exists(output_dir, repo_name)

    if not force and pa_done and pr_json_done:
        print(f"[SKIP] PA canonical files already exist (pass --force to re-extract)")
    else:
        result = extract_repository_data(
            repo_owner=repo_owner,
            repo_name=repo_name,
            output_base_dir=str(output_dir),
            save_json=True,
            save_csv=True,
            include_commits=include_commits,
            include_files=include_files,
            include_comments=include_comments,
        )
        if result.get("status") != "success":
            print(f"[FAIL] Extraction failed: {result.get('errors')}")
            return False

    # --- Issues (CA-specific) ---
    if include_issues:
        if not force and _issues_json_exists(output_dir, repo_name):
            print(f"[SKIP] Issues JSON already exists")
        else:
            try:
                extractor = PullRequestExtractor(
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    need_auth=True,
                )
                extract_and_save_issues(extractor, output_dir, repo_name, force)
            except Exception as e:
                print(f"[WARN] Issue extraction failed: {e} (CA issues will fall back to API)")

    # --- commits_by_day (CA-specific, derived — no API call) ---
    if include_commits:
        derive_commits_by_day(output_dir, repo_name, force)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified GitHub data extraction for processAnalysis + collabAnalysis"
    )
    parser.add_argument("--repo-owner", required=True,
                        help="GitHub organisation or user")
    parser.add_argument("--repo-name", required=True,
                        help="Repository name or comma-separated list")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "data"),
                        help="Base output directory (default: ./data)")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even when canonical files already exist")
    parser.add_argument("--no-issues",   action="store_true",
                        help="Skip issue extraction (CA issues will use API)")
    parser.add_argument("--no-commits",  action="store_true",
                        help="Skip commit extraction")
    parser.add_argument("--no-files",    action="store_true",
                        help="Skip file-change extraction")
    parser.add_argument("--no-comments", action="store_true",
                        help="Skip comment extraction")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    repos = [r.strip() for r in args.repo_name.split(",") if r.strip()]
    failed = []

    print(f"Output directory: {output_dir}")
    print(f"Repos to process: {repos}")

    for repo in repos:
        ok = extract_one(
            repo_owner=args.repo_owner,
            repo_name=repo,
            output_dir=output_dir,
            force=args.force,
            include_commits=not args.no_commits,
            include_files=not args.no_files,
            include_comments=not args.no_comments,
            include_issues=not args.no_issues,
        )
        if not ok:
            failed.append(repo)

    print(f"\n{'='*70}")
    if failed:
        print(f"[DONE] Completed with failures: {failed}")
        sys.exit(1)
    print(f"[DONE] All {len(repos)} repo(s) extracted successfully.")


if __name__ == "__main__":
    main()
