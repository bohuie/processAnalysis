import os
import json
import pandas as pd
import unicodedata
import re

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data", "csv")
CONF_DIR = os.path.join(ROOT_DIR, "confidential")
OUTPUT_FILE = os.path.join(DATA_DIR, "merged_metadata.csv")

# === Helper functions =======================================
def normalize_name(s):
    """Remove accents, lowercase, trim, and keep only first + last tokens."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
    s = s.strip().lower()
    parts = s.split()
    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1]}"

def simplify_name(s):
    """Lowercase, remove accents/punctuation, replace hyphens with spaces."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
    s = s.lower().replace("-", " ")
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())

def name_key(fn, ln):
    """Unified string key for joining."""
    return simplify_name(f"{fn} {ln}")

def parse_name(name):
    if not isinstance(name, str):
        return pd.Series({"first_name": None, "last_name": None})
    parts = name.strip().split()
    if len(parts) == 0:
        return pd.Series({"first_name": None, "last_name": None})
    if len(parts) == 1:
        return pd.Series({"first_name": parts[0], "last_name": None})
    return pd.Series({"first_name": parts[0], "last_name": parts[-1]})


def main():
    print("\n Please enter only the filenames (not full paths).")
    print("   • CSV files must be inside: data/csv/")
    print("   • anonymized_usernames JSON file must be inside: confidential/")
    print("   • modify the fieldnames of the df as apparent in your files\n")

    GITHUB_FP  = os.path.join(DATA_DIR, input("  → GitHub usernames CSV filename (e.g., Github_Usernames.csv): ").strip())
    CONSENT_FP = os.path.join(DATA_DIR, input("  → Informed consent CSV filename (e.g., Course_Informed_Consent.csv): ").strip())
    GRADES_FP  = os.path.join(DATA_DIR, input("  → Grades CSV filename (e.g., Course_Gradebook.csv): ").strip())
    ANON_FP    = os.path.join(CONF_DIR, "anonymized_usernames.json")

    # === Load input files =======================================
    print("\n[INFO] Loading input files...")
    try:
        github_df  = pd.read_csv(GITHUB_FP)
        consent_df = pd.read_csv(CONSENT_FP)
        grades_df  = pd.read_csv(GRADES_FP)
        with open(ANON_FP, "r") as f:
            anon_map = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load files: {e}")
        return

    # === GitHub Info ============================================
    github_df.columns = github_df.columns.str.strip()
    github_df = github_df.rename(columns={
        "Team": "team_number",
        "First name": "first_name",
        "Last Name": "last_name",
        "Github username": "github_username",
    })
    # Check if columns exist before subsetting
    expected_cols = ["team_number", "first_name", "last_name", "github_username"]
    if not all(col in github_df.columns for col in expected_cols):
        print(f"[ERROR] GitHub CSV missing columns. Expected: {expected_cols}, Found: {list(github_df.columns)}")
        # Try to proceed or exit? Let's exit to be safe as in original script logic it would crash
        return

    github_df = github_df[expected_cols].copy()
    github_df["team_number"] = github_df["team_number"].astype(str).str.strip()

    # === Consent Data ===========================================
    consent_df = consent_df.rename(columns={
        "Q1": "consent_text",
        "Q3_1": "name",
        "RecordedDate": "timestamp",
    })
    mask_real = ~consent_df["timestamp"].astype(str).str.contains("Recorded Date|\\{", na=True)
    consent_df = consent_df[mask_real].copy()
    consent_df["timestamp"] = pd.to_datetime(consent_df["timestamp"], errors="coerce")
    consent_df = consent_df.dropna(subset=["timestamp"])
    consent_df = consent_df.sort_values("timestamp").drop_duplicates(subset=["name"], keep="last")

    name_split = consent_df["name"].apply(parse_name)
    consent_df = pd.concat([consent_df, name_split], axis=1)
    consent_df["consent_given"] = consent_df["consent_text"].astype(str).str.lower().apply(
        lambda x: ("i consent" in x) and ("do not" not in x)
    )
    consent_df = consent_df[["first_name", "last_name", "consent_given"]].copy()

    # === Grades Data ============================================
    grades_df = grades_df.rename(columns={
        "Student": "student_name",
        "Overall Grade (1724270)": "final_grade",
    })
    grades_df = grades_df[
        grades_df["student_name"].notna()
        & ~grades_df["student_name"].astype(str).str.contains("Points Possible", na=False)
    ].copy()

    split = grades_df["student_name"].astype(str).str.split(",", n=1, expand=True)
    grades_df["last_name"]  = split[0].str.strip()
    grades_df["first_name"] = split[1].str.strip().str.split().str[0]
    grades_df["final_grade"] = pd.to_numeric(grades_df["final_grade"], errors="coerce")
    grades_df = grades_df[["first_name", "last_name", "final_grade"]]

    # === Normalize names ========================================
    for df in [github_df, consent_df, grades_df]:
        df["first_name"] = df["first_name"].apply(normalize_name)
        df["last_name"]  = df["last_name"].apply(normalize_name)

    # === Fix known name mismatches ==============================
    manual_name_overrides = {
        # github_username : (first_name, last_name) as they appear in gradebook
    }

    # Apply manual overrides directly to GitHub dataframe
    for idx, row in github_df.iterrows():
        uname = str(row["github_username"]).strip().lower()
        if uname in manual_name_overrides:
            fn, ln = manual_name_overrides[uname]
            github_df.at[idx, "first_name"] = normalize_name(fn)
            github_df.at[idx, "last_name"] = normalize_name(ln)


    github_df = github_df[~github_df["github_username"].str.lower().eq("")]

    # === Initial merge ==========================================
    merged = (
        github_df
        .merge(consent_df, on=["first_name", "last_name"], how="left")
        .merge(grades_df,  on=["first_name", "last_name"], how="left")
    )
    merged["consent_given"] = merged["consent_given"].fillna(False)
    merged["anonymized_name"] = merged["github_username"].map(anon_map).fillna("")


    # === Fallback auto-matching =================================
    grade_map = {}
    for _, row in grades_df.iterrows():
        key = name_key(row["first_name"], row["last_name"])
        if key not in grade_map:
            grade_map[key] = row["final_grade"]

    def get_auto_grade(fn, ln):
        key = name_key(fn, ln)
        if key in grade_map:
            return grade_map[key]
        fn_simpl = simplify_name(fn).split()[0] if fn else ""
        ln_simpl = simplify_name(ln).split()[-1] if ln else ""
        for gkey, val in grade_map.items():
            if gkey.endswith(ln_simpl) and gkey.startswith(fn_simpl[:3]):
                return val
        return None

    missing_mask = merged["final_grade"].isna()
    filled_count = 0
    for idx, row in merged[missing_mask].iterrows():
        val = get_auto_grade(row["first_name"], row["last_name"])
        if pd.notna(val):
            merged.at[idx, "final_grade"] = val
            filled_count += 1

    # === Compute team averages ==================================
    if "team_number" in merged.columns and "final_grade" in merged.columns:
        avg_by_team = (
            merged.groupby("team_number")["final_grade"]
            .mean()
            .rename("avg_team_grade")
            .reset_index()
        )
        merged = merged.merge(avg_by_team, on="team_number", how="left")
        
        print("\n[INFO] Average team grades (all students):")
        for _, r in avg_by_team.iterrows():
            print(f"   Team {r['team_number']}: {r['avg_team_grade']:.2f}")

    # === Save ====================================================
    os.makedirs(DATA_DIR, exist_ok=True)
    merged.to_csv(OUTPUT_FILE, index=False)

    total_students = len(github_df)
    consented = int(merged["consent_given"].sum())
    teams = merged["team_number"].nunique()

    print(f"[INFO] Total students in GitHub list: {total_students}")
    print(f"[INFO] Consented: {consented} | Not consented: {total_students - consented}")
    print(f"[INFO] Teams detected: {teams}")
    print(f"[INFO] Filled {filled_count} additional grades automatically via fallback matching.")

    unmatched = merged[merged["final_grade"].isna()][["first_name", "last_name", "github_username"]]
    if not unmatched.empty:
        print("\n[WARN] Students still missing final_grade after fallback:")
        for _, r in unmatched.iterrows():
            print(f"   {r['first_name']} {r['last_name']} ({r['github_username']})")
    else:
        print("\n[INFO] All students successfully matched to a final_grade.")

    print(f"[✅] Saved merged_metadata.csv → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()