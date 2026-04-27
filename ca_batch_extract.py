"""
Batch extraction of GitHub PR and review-comment data for the combined PA+CA workflow.

Reads REPO_OWNER, REPO_NAMES from the environment and extracts GitHub data for
every repo, saving CSVs to data/csv/.

These CSVs complement the JSON output from scripts/unified_github_data_pull.py.
"""
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(verbose=False)

from src.extractors.pull_request_extractor import PullRequestExtractor
from src.utils.file_path import get_project_data_csv_folder


_BLACKLISTED = {"github-classroom[bot]", "dependabot[bot]"}


def _save_to_csv(rows: list, out_path: Path, label: str) -> None:
    if not rows:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {label}: {len(rows)} rows → {out_path}")


def main():
    repo_owner = os.environ.get("REPO_OWNER", "").strip()
    repo_names_raw = os.environ.get("REPO_NAMES", "").strip()

    if not repo_owner:
        print("ERROR: REPO_OWNER is not set in the environment")
        sys.exit(1)

    repo_names = [r.strip() for r in repo_names_raw.split(",") if r.strip()]
    if not repo_names:
        print("ERROR: REPO_NAMES is not set in the environment")
        sys.exit(1)

    csv_folder = get_project_data_csv_folder()
    csv_folder.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("Batch Extraction")
    print(f"{'='*60}")
    print(f"Org   : {repo_owner}")
    print(f"Repos : {len(repo_names)}")
    print(f"Output: {csv_folder}")
    print()

    failed = []
    for repo_name in repo_names:
        print(f"Extracting: {repo_owner}/{repo_name}")
        try:
            extractor = PullRequestExtractor(repo_owner, repo_name)

            prs = [
                pr for pr in extractor.extract_all_pull_requests(state="all")
                if (pr.get("user") or {}).get("login") not in _BLACKLISTED
            ]
            print(f"  PRs: {len(prs)}")
            _save_to_csv(
                prs,
                csv_folder / repo_name / f"{repo_name}_all_pull_requests.csv",
                "PRs saved",
            )

            all_comments = []
            for pr in prs:
                pr_id = pr.get("number")
                if pr_id:
                    comments = extractor.extract_pr_review_comments(pr_id)
                    all_comments.extend(
                        c for c in comments
                        if (c.get("user") or {}).get("login") not in _BLACKLISTED
                    )
            print(f"  Review comments: {len(all_comments)}")
            _save_to_csv(
                all_comments,
                csv_folder / repo_name / f"{repo_name}_review-comments.csv",
                "Review comments saved",
            )

        except Exception as exc:
            print(f"  ERROR: {exc}")
            failed.append(repo_name)

    print(f"\n{'='*60}")
    if failed:
        print(f"Finished with {len(failed)} failure(s): {', '.join(failed)}")
    else:
        print("Extraction complete — all repos succeeded.")
    print(f"CSVs saved to: {csv_folder}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
