# 🧠 Collaboration Analysis – Replication Package

This repository provides a complete pipeline for analyzing collaboration and code structure patterns in GitHub repositories.  
It uses the **GitHub API** and **LLM-based analysis (Ollama 3.2:3B)** to extract, enrich, clean, and visualize repository pull request (PR) and code structure data.

---

## 📂 Overview

The workflow consists of several stages — from data extraction to graph generation and statistical analysis.

### Main Features
- 🔍 **Data Extraction:** Automatically pulls PR and repository metadata via GitHub API.
- 🧩 **Data Enrichment:** Enhances raw PR data with communication and structure insights.
- 🧼 **Data Cleaning & Preprocessing:** Standardizes data for analysis.
- 🤖 **Bot Filtering:** Removes automated bot accounts from analysis.
- 📊 **Graph Generation:** Visualizes PR networks, branching behavior, and collaboration patterns.
- 📈 **Statistical Analysis:** Provides summary statistics of repository activity.

---

## ⚙️ Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/processAnalysis.git
cd processAnalysis
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate    # (Mac/Linux)
venv\Scripts\activate       # (Windows)
```

### 3. Install Dependencies
Install Python dependencies listed in `requirements.txt` (if not present, manually include your project's libraries such as `pandas`, `requests`, `tqdm`, `ollama`, etc.):
```bash
pip install -r requirements.txt
```

---

## 🤖 Ollama Setup

This project uses **Ollama 3.2:3B** for analyzing PR communications and code structure.

### 1. Install Ollama
Follow instructions from [Ollama's official site](https://ollama.com/download).

### 2. Pull the required model
```bash
ollama pull llama3.2:3b
```

### 3. Start the Ollama server
```bash
ollama serve
```

Keep this running in the background while executing scripts that depend on Ollama.

---

## 🚀 How to Run

Below is the **recommended execution order**:

### 1. Data Collection  
Run `app.py` to pull data for selected repositories.
```bash
python scripts/app.py
```
⚠️ Make sure you've added your target repositories in the `repositories` list before running.

### 2. Data Enrichment  
Run enrichment and PR/communication labeling (from repo root):
```bash
python enrich_output/overwrite_files.py
python event_labelling/PR/pr_label.py
python event_labelling/Communication/comm_label.py
```

### 3. Code Structure & Branching Analysis  
Requires a running Ollama instance. There are two entry points; run either from the repository root:
Run the orchestration script from the repository root:
```bash
python event_labelling/CodeStructure_Branching/main.py
```

### 4. Data Cleaning  
```bash
python process_model/clean.py
```

### 5. Preprocessing (for Graphs)  
Keep only one section active if working with split datasets.
```bash
python process_model/preprocessing.py
```

### 6. Graph Generation  
```bash
python process_model/graphing.py
```

### 7. Statistical Analysis (Optional)  
To get general repository statistics run the project-level analysis script from the repo root:
```bash
python analysis.py
```

---

## 🛠️ Utility Modules

### Bot Filter (`src/utils/botFilter.py`)

A reusable utility module for filtering bot accounts located in `src/utils/botFilter.py`.

**Features:**
- Detects common bot patterns (dependabot, renovate, GitHub Actions, etc.)
- Flexible filtering functions for pandas DataFrames
- Extensible with custom bot patterns
- Verbose logging for transparency

**Usage Example:**
```python
from src.utils.botFilter import remove_bot_prs, remove_bot_commits, filter_bots_from_multiple_columns

# Filter bot PRs
clean_prs_df = remove_bot_prs(prs_df)

# Filter bot commits
clean_commits_df = remove_bot_commits(commits_df)

# Custom filtering
clean_df = filter_bots_from_multiple_columns(df, username_columns=['pr_author', 'merged_by'])
```

**Available Functions (examples):**
- `is_bot_username()` - Check if a username is a bot
- `filter_bots_from_dataframe()` - Filter bots from any DataFrame
- `remove_bot_prs()` - Convenience function for PR data
- `remove_bot_commits()` - Convenience function for commit data
- `filter_bots_from_multiple_columns()` - Filter based on multiple columns

---

## 📊 Output

The scripts produce:
- **Cleaned CSV files** with enriched PR and code structure data.
- **Graph visualizations** showing collaboration patterns, code structure networks, and branching metrics.
- **Summary statistics** in CSV or plotted form.
- **Bot-filtered datasets** for accurate human collaboration analysis.

---

## 🧱 Project Structure

```
processAnalysis/
├── README.md
├── analysis.py                        # Project-level analysis runner
├── requirements.txt
├── scripts/
│   └── app.py                         # Data extraction wrapper (uses src.extractors)
├── documentation/                     # User-facing documentation
│   ├── analysis.md
│   ├── app.md
│   └── code_structure_and_branching.md
├── src/                               # Core libraries used by scripts
│   ├── extractors/
│   │   └── pull_request_extractor.py
│   └── utils/
│       ├── botFilter.py
│       ├── ollama_offline.py
│       └── ...
├── enrich_output/
│   └── overwrite_files.py             # Data enrichment helpers
├── event_labelling/
│   ├── CodeStructure_Branching/
│   │   ├── main.py                     # Orchestration for branching/structure labeling
│   │   ├── label_branch_names.py
│   │   ├── label_features_per_branch.py
│   │   ├── label_feature_size.py
│   │   ├── label_refactor_size.py
│   │   ├── label_pr_status.py
│   │   └── clean_lable.py
│   ├── PR/
│   │   ├── pr_label.py
│   │   ├── helpers_pr.py
│   │   └── prep_data.py
│   └── Communication/
│       └── comm_label.py
├── process_model/
│   ├── clean.py
│   ├── preprocessing.py
│   └── graphing.py
├── test/
│   ├── test_llm_output.py
│   ├── testApp.py
│   └── testBot_filter.py
├── data/
│   └── csv/                           # Output CSVs and processed data (per-team folders)
├── confidential/                      # Optional: anonymization mapping, secrets (gitignored)
└── requirements.stable.txt
```

---

## 🔧 Configuration

### GitHub API Token
Set your GitHub API token as an environment variable:
```bash
export GITHUB_TOKEN='your_token_here'
```

### Repository Configuration
Update the following variables in `scripts/app.py`:
- `REPOSITORIES` - List of repositories to analyze
- `REPO_OWNER` - Repository owner/username
- `ORG_NAME` - Organization name (if applicable)

### Anonymization (Optional)
If using anonymized data, create a mapping file:
```json
// confidential/anonymized_usernames.json
{
  "real_username_1": "Anon_User_1",
  "real_username_2": "Anon_User_2"
}
```

Then set `ANONYMIZE = True` in the relevant scripts.

---

## 🧩 Notes

- **GitHub API Token:** Required for data collection. Set as `GITHUB_TOKEN` environment variable.
- **Bot Filtering:** Automatically applied during data processing. Customize patterns in `botFilter.py` if needed.
- **Anonymization:** Update paths in scripts if using anonymized datasets.
- **Working Directory:** All scripts assume execution from the project root directory.
- **Ollama Dependency:** Code structure analysis requires a running Ollama server.

---

## 🐛 Testing

Run unit tests to verify functionality:
```bash
# Test bot filtering
python test/testBot_filter.py

# Test data cleaning
python test/testClean.py

# Test app functionality
python test/testApp.py
```

---