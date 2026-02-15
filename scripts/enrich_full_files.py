import sys
import traceback
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional, Set

# Fix Python path to find src module
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")
print(f"[DEBUG] Python path: {sys.path[:3]}")

# Import extraction functionality
try:
    from src.extractors.pull_request_extractor import PullRequestExtractor
    print("[DEBUG] Successfully imported PullRequestExtractor")
except ImportError as e:
    print(f"[ERROR] Failed to import PullRequestExtractor: {e}")
    sys.exit(1)

def enrich_full_files_for_repo(
    repo_owner: str,
    repo_name: str,
    output_base_dir: str = "./data",
    allowed_ext: Optional[Set[str]] = None,
) -> Path:
    """Build a CSV of full file contents at each PR head commit for files changed in those PRs."""

    exts = allowed_ext or {
        ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".rb", ".go", ".kts", ".cc",
        ".cpp", ".c", ".h", ".hpp", ".cs", ".kt", ".rs", ".php", ".swift", ".sh"
    }
    
    # Create output directories
    base_path = Path(output_base_dir).resolve()
    csv_dir = base_path / "csv" / repo_name
    csv_dir.mkdir(parents=True, exist_ok=True)

    # Full Files at PR Head CSV
    out_csv = csv_dir / f"{repo_name}_full_files_at_pr_head.csv"

    print("=" * 80)
    print(f"FULL-FILE ENRICHMENT: {repo_owner}/{repo_name}")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output:  {out_csv}")
    print("=" * 80)

    # Initialize extractor
    extractor = PullRequestExtractor(
        repo_owner=repo_owner,
        repo_name=repo_name,
        need_auth=True,
    )

    # Extract pull requests
    print("[INFO] Fetching pull requests...")
    pull_requests = extractor.extract_all_pull_requests(state="all")
    
    # Pre-cache PR file lists to avoid redundant API calls
    print("[INFO] Pre-caching PR file lists...")

    file_changes_cache = {}
    for pr in pull_requests:
        pr_id = pr["number"]  # GitHub PR number
        file_changes_cache[pr_id] = extractor.extract_pr_file_changes(pr_id)

    print(f"[INFO] Cached file lists for {len(file_changes_cache)} PRs")

    # Write the full-file CSV 
    fieldnames = ["pr_id", "head_sha", "file_path", "status", "previous_filename", "content"]
    rows = []
    cache = {}  # (head_sha, file_path) -> content
    
    # Decide whether a changed file should be included in full-file enrichment
    def should_include_file(path: str, status: str) -> bool:
        if not path:
            return False
        if status == "removed":
            return False
        lower = path.lower()
        return any(lower.endswith(ext) for ext in exts)
    
    # Resolve the head commit SHA for a pull request
    def get_head_sha_for_pr(pr: dict) -> Optional[str]:
        head_sha = (pr.get("head") or {}).get("sha")
        if head_sha:
            return head_sha
        pr_id_local = pr.get("number")
        if not pr_id_local:
            return None
        full = extractor.extract_pull_request_by_id(pr_id_local)
        return (full.get("head") or {}).get("sha") if full else None
    
    # Extract the full contents of a file at a specific commit SHA with caching
    def fetch_file_content_cached(head_sha: str, path: str) -> Optional[str]:
        key = (head_sha, path)
        if key in cache:
            return cache[key]
        content = extractor.extract_file_content_at_ref(path=path, ref=head_sha)
        cache[key] = content
        return content

    print(f"[INFO] Fetching full file contents for {len(pull_requests)} PRs...")

    for pr_idx, pr in enumerate(pull_requests, 1):
        if pr_idx % max(1, len(pull_requests) // 10) == 0:
            print(f"[INFO] Full-file progress: {pr_idx}/{len(pull_requests)} PRs")

        pr_id = pr.get("number")
        if pr_id is None:
            continue

        head_sha = get_head_sha_for_pr(pr)
        if not head_sha:
            continue

        files = file_changes_cache.get(pr_id, [])
        for f in files:
            path = f.get("filename")
            status = f.get("status")
            previous_filename = f.get("previous_filename")

            if not should_include_file(path, status):
                continue

            content = fetch_file_content_cached(head_sha, path)
            if not content:
                continue

            rows.append({
                "pr_id": pr_id,
                "head_sha": head_sha,
                "file_path": path,
                "status": status,
                "previous_filename": previous_filename,
                "content": content,
            })

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[SUCCESS] Wrote {len(rows)} rows → {out_csv}")
    return out_csv


if __name__ == "__main__":

    # ==================== CONFIGURATION ====================

    REPO_OWNER = "COSC-499-W2023"
    REPO_NAMES = [
        "year-long-project-team-15"
    ]

    OUTPUT_DIR = "./data"

    # (Optional)
    ALLOWED_EXT = None  # Example: {".java"} or None for default multi-language set

    # ==================== EXECUTION ====================

    print("\n" + "=" * 80)
    print("FULL-FILE ENRICHMENT (CONFIG MODE)")
    print("=" * 80)
    print(f"Working directory: {Path.cwd()}")
    print(f"Script location: {Path(__file__).parent}")
    print(f"Total repositories to process: {len(REPO_NAMES)}")
    print("=" * 80)

    all_outputs = []
    failed_repos = []

    try:
        for idx, repo_name in enumerate(REPO_NAMES, 1):
            print(f"\n[{idx}/{len(REPO_NAMES)}] Processing: {repo_name}")

            try:
                out_csv = enrich_full_files_for_repo(
                    repo_owner=REPO_OWNER,
                    repo_name=repo_name,
                    output_base_dir=OUTPUT_DIR,
                    allowed_ext=ALLOWED_EXT,
                )
                all_outputs.append(out_csv)

            except Exception as e:
                print(f"[ERROR] Failed to process {repo_name}: {e}")
                failed_repos.append((repo_name, str(e)))
                traceback.print_exc()

        print("\n" + "=" * 80)
        print("ENRICHMENT SUMMARY")
        print("=" * 80)
        print(f"Successful: {len(all_outputs)}")
        print(f"Failed: {len(failed_repos)}")

        if failed_repos:
            print("\n❌ FAILED REPOSITORIES:")
            for repo_name, err in failed_repos:
                print(f"  - {repo_name}: {err}")
            sys.exit(1)
        else:
            print("\n✅ ALL REPOSITORIES ENRICHED SUCCESSFULLY")

        print("=" * 80)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 80)
    print(f"✅ SUCCESS - Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

