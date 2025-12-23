"""
Branch Name Labeling: Meaningful vs Random
Uses LLM to determine if branch names are descriptive.
"""
import pandas as pd
import re
from tqdm import tqdm


def get_unique_branch_names(prs_df):
    """Extract unique branch names regardless of PR ID presence."""
    if "head_branch" not in prs_df.columns:
        print("    No 'head_branch' column found in PR data")
        return []
    
    branch_names = prs_df["head_branch"].dropna().unique()
    branch_names = [str(branch).strip() for branch in branch_names if str(branch).strip()]
    
    print(f"    Found {len(branch_names)} unique branch names")
    return branch_names


def create_branch_struct(prs_df):
    """Create a mapping of branch names to their PR IDs and authors."""
    branch_mapping = {}
    
    if "head_branch" not in prs_df.columns or "pr_id" not in prs_df.columns:
        return branch_mapping
    
    for _, row in prs_df.iterrows():
        branch_name = str(row.get("head_branch", "")).strip()
        pr_id = row.get("pr_id")
        pr_author = row.get("pr_author", "unknown")
        created_at = row.get("created_at")
        
        if not branch_name or pd.isna(pr_id):
            continue
            
        if branch_name not in branch_mapping:
            branch_mapping[branch_name] = []
        
        branch_mapping[branch_name].append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": created_at
        })
    
    multi_pr_branches = {branch: prs for branch, prs in branch_mapping.items() if len(prs) > 1}
    if multi_pr_branches:
        print(f"    Found {len(multi_pr_branches)} branches used by multiple PRs")
        for branch, prs in list(multi_pr_branches.items())[:5]:
            print(f"      '{branch}': {len(prs)} PRs")
    
    return branch_mapping


def assess_branch_meaningfulness(ask_llm, branch_name, pr_title, pr_description):
    """Ask Ollama if the branch name is meaningful based on PR context.
    
    Returns:
        tuple: (label, reason, confidence_score, llm_output)
        - label: "Meaningful Branch Name" or "Random Branch Name"
        - reason: The LLM's reasoning for the decision
        - confidence_score: A score from 0-100 indicating confidence
        - llm_output: The full raw output from the LLM
    """
    prompt = f"""
        You are assessing whether this Git branch name clearly reflects the PR purpose.

        Branch name: {branch_name}
        PR title: {pr_title}
        PR description: {pr_description}

        Please provide your assessment in the following format:
        
        REASON: [Your reasoning explaining why the branch name is meaningful or random]
        PREDICTION: [Either "meaningful" or "random"]
        CONFIDENCE: [A number from 0-100 indicating how confident you are in your prediction]

        Guidelines:
        - If the branch name clearly relates to the feature, fix, or topic (e.g., 'feature/login', 'fix/navbar', 'refactor_api'), it is "meaningful".
        - If it is generic, unclear, random, or unrelated (e.g., 'test', 'final', 'update', 'misc', 'main', 'newbranch'), it is "random".
        - Confidence should be high (80-100) when the branch name clearly matches or clearly doesn't match the PR purpose.
        - Confidence should be lower (50-79) when there's some ambiguity.
        - Confidence should be very low (0-49) only when you're very uncertain.
    """
    llm_output = ask_llm(prompt).strip()
    
    # Parse the response to extract reason, prediction, and confidence
    reason = ""
    prediction = ""
    confidence_score = None
    
    # Try to extract REASON
    reason_match = re.search(r'REASON:\s*(.+?)(?=PREDICTION:|CONFIDENCE:|$)', llm_output, re.IGNORECASE | re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip()
    
    # Try to extract PREDICTION
    prediction_match = re.search(r'PREDICTION:\s*(meaningful|random)', llm_output, re.IGNORECASE)
    if prediction_match:
        prediction = prediction_match.group(1).lower()
    else:
        # Fallback: check if "meaningful" or "random" appears in the output
        answer = llm_output.lower()
        if "meaningful" in answer:
            prediction = "meaningful"
        else:
            prediction = "random"
    
    # Try to extract CONFIDENCE score
    confidence_match = re.search(r'CONFIDENCE:\s*(\d+)', llm_output, re.IGNORECASE)
    if confidence_match:
        try:
            confidence_score = int(confidence_match.group(1))
            # Clamp to 0-100 range
            confidence_score = max(0, min(100, confidence_score))
        except ValueError:
            confidence_score = None
    else:
        # Try to find any number in the confidence section
        confidence_section = re.search(r'CONFIDENCE:.*?(\d+)', llm_output, re.IGNORECASE | re.DOTALL)
        if confidence_section:
            try:
                confidence_score = int(confidence_section.group(1))
                confidence_score = max(0, min(100, confidence_score))
            except ValueError:
                confidence_score = None
    
    # If we couldn't extract reason, use a fallback
    if not reason:
        reason = "No explicit reason provided by LLM"
    
    # If we couldn't extract confidence, set a default based on prediction presence
    if confidence_score is None:
        confidence_score = 50  # Default to medium confidence if not found
    
    # Determine label
    if prediction == "meaningful":
        label = "Meaningful Branch Name"
    else:
        label = "Random Branch Name"

    return label, reason, confidence_score, llm_output


def label_branch_names(prs_df, ask_llm, run_timestamp):
    """Label: meaningful, random - Uses LLM to determine if branch names are descriptive.
    
    For each branch, collects ALL pr_titles and pr_descriptions that belong to it,
    then passes them all to the LLM for assessment.
    """
    print("  Evaluating branch naming via Ollama...")
    result_rows = []
    llm_reasoning_rows = []

    branch_mapping = create_branch_struct(prs_df)
    unique_branches = get_unique_branch_names(prs_df)
    
    if not unique_branches:
        print("    No branch names found to evaluate")
        return pd.DataFrame(), pd.DataFrame()

    # Build comprehensive context for each branch: all PRs and their info
    branch_pr_info = {}
    for branch_name, pr_list in branch_mapping.items():
        pr_titles = []
        pr_descriptions = []
        
        for pr_info in pr_list:
            pr_id = pr_info["pr_id"]
            pr_row = prs_df[prs_df["pr_id"] == pr_id]
            if not pr_row.empty:
                pr_row = pr_row.iloc[0]
                title = str(pr_row.get("pr_title", "")).strip()
                description = str(pr_row.get("pr_description", "")).strip()
                
                if title:
                    pr_titles.append(title)
                if description:
                    pr_descriptions.append(description)
        
        branch_pr_info[branch_name] = {
            "pr_titles": pr_titles,
            "pr_descriptions": pr_descriptions,
            "pr_count": len(pr_list)
        }

    # Iterate only branches that actually have PRs (branch_mapping keys).
    for branch_name in tqdm(list(branch_mapping.keys()), desc="  Branch naming"):
        if branch_name.lower() in ["main", "master"]:
            if branch_name in branch_mapping:
                for pr_info in branch_mapping[branch_name]:
                    result_rows.append({
                        "pr_id": pr_info["pr_id"],
                        "pr_author": pr_info["pr_author"],
                        "created_at": pr_info.get("created_at"),
                        "branch_name": branch_name,
                        "event": "Random Branch Name",
                        "main_label": "Branch Name",
                        "llm_output": "auto-labeled: main/master branch",
                        "llm_timestamp": run_timestamp
                    })
            continue

        # Get all PR titles and descriptions for this branch
        pr_titles = branch_pr_info[branch_name]["pr_titles"]
        pr_descriptions = branch_pr_info[branch_name]["pr_descriptions"]
        pr_count = branch_pr_info[branch_name]["pr_count"]
        
        # Combine all titles and descriptions into a single context
        all_pr_context = f"PR Count: {pr_count}\n"
        if pr_titles:
            all_pr_context += f"PR Titles:\n" + "\n".join(f"  - {title}" for title in pr_titles) + "\n"
        if pr_descriptions:
            all_pr_context += f"PR Descriptions:\n" + "\n".join(f"  - {desc}" for desc in pr_descriptions) + "\n"

        try:
            name_label, reason, confidence_score, llm_raw = assess_branch_meaningfulness(
                ask_llm, branch_name, all_pr_context, ""
            )
        except Exception as e:
            # Fallback when LLM call fails — mark as random with medium confidence
            print(f"[WARN] LLM assessment failed for branch '{branch_name}': {e}")
            name_label = "Random Branch Name"
            reason = f"LLM error: {e}"
            confidence_score = 50
            llm_raw = f"[ERROR] LLM unavailable: {e}"
        
        if branch_name in branch_mapping:
            for pr_info in branch_mapping[branch_name]:
                result_rows.append({
                    "pr_id": pr_info["pr_id"],
                    "pr_author": pr_info["pr_author"],
                    "created_at": pr_info.get("created_at"),
                    "branch_name": branch_name,
                    "event": name_label,
                    "main_label": "Branch Name",
                    "llm_output": llm_raw,
                    "llm_timestamp": run_timestamp
                })
                
                llm_reasoning_rows.append({
                    "pr_id": pr_info["pr_id"],
                    "pr_author": pr_info["pr_author"],
                    "created_at": pr_info.get("created_at"),
                    "branch_name": branch_name,
                    "pr_titles": " | ".join(pr_titles),
                    "pr_descriptions": " | ".join(pr_descriptions),
                    "pr_count": pr_count,
                    "branch_naming_label": name_label,
                    "llm_reasoning": reason,
                    "llm_confidence_score": confidence_score,
                    "llm_full_output": llm_raw,
                    "llm_timestamp": run_timestamp
                })

    labels_df = pd.DataFrame(result_rows) if result_rows else pd.DataFrame()
    llm_reasoning_df = pd.DataFrame(llm_reasoning_rows) if llm_reasoning_rows else pd.DataFrame()

    return labels_df, llm_reasoning_df