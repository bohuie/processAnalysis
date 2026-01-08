# 🧠 Collaboration Analysis – Replication Package

This repository provides a complete pipeline for analyzing collaboration and code structure patterns in GitHub repositories.  
It uses the **GitHub API** and **LLM-based analysis (Ollama 3.2:3B by default, Groq optional)** to extract, enrich, clean, and visualize repository pull request (PR) and code structure data.

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
Install Python dependencies listed in `requirements.txt` (Python 3.9+ recommended):
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Create a `.env` file (or edit the existing one) at the repo root. Key vars:

```
AI_MODE=offline        # offline -> local Ollama, online -> Groq API
GROQ_API_KEY=...       # only needed when AI_MODE=online
GROQ_MODEL_NAME=llama-3.1-8b-instant  # optional override
GITHUB_TOKEN=...       # required for GitHub API extraction
```
If you want purely offline runs, set `AI_MODE=offline` and ensure Ollama is running. If you want Groq, set `AI_MODE=online` and supply `GROQ_API_KEY`.

---

## 🤖 LLM Setup (Ollama by default, Groq optional)

This project prefers **Ollama 3.2:3B** for offline analysis. Groq can be enabled via `AI_MODE=online` when you supply `GROQ_API_KEY`.

### 1. Install Ollama
Follow instructions from [Ollama's official site](https://ollama.com/download).

### 2. Pull the required model
```bash
ollama pull llama3.2:3b
```

### 3. Start the Ollama server (for AI_MODE=offline)
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
```bash
python enrich_output/overwrite_files.py
python event_labelling/Utility/pr_communication_label.py
```

### 3. Code Structure & Branching Analysis  
Respects `AI_MODE` (offline→Ollama, online→Groq). Run from repo root:
```bash
python -m event_labelling.CodeStructure_Branching.main
python event_labelling/Utility/csvFix.py
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
To get general repository statistics:
```bash
python event_labelling/analysis.py
```

---

## 🛠️ Utility Modules

### Bot Filter (`event_labelling/Utility/botFilter.py`)

A reusable utility module for filtering bot accounts from GitHub data.

**Features:**
- Detects 20+ common bot patterns (dependabot, renovate, GitHub Actions, etc.)
- Flexible filtering functions for DataFrames
- Extensible with custom bot patterns
- Includes verbose logging for transparency

**Usage Example:**
```python
from event_labelling.Utility.bot_filter import remove_bot_prs, remove_bot_commits

# Filter bot PRs
clean_prs_df = remove_bot_prs(prs_df)

# Filter bot commits
clean_commits_df = remove_bot_commits(commits_df)

# Custom filtering
from event_labelling.Utility.bot_filter import filter_bots_from_dataframe
clean_df = filter_bots_from_dataframe(df, username_column='reviewer')
```

**Available Functions:**
- `is_bot_username()` - Check if a username is a bot
- `filter_bots_from_dataframe()` - Filter bots from any DataFrame
- `remove_bot_prs()` - Convenience function for PR data
- `remove_bot_commits()` - Convenience function for commit data
- `get_bot_usernames()` - List all bot usernames found
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
collabAnalysis/
├── documentation/
│   ├── analysis.md             # Analysis documentation
│   ├── app.md                  # App usage guide
│   └── csvFix.md               # CSV fixing documentation
├── scripts/
│   └── app.py                  # Fetches data via GitHub API
├── enrich_output/
│   └── overwrite_files.py      # Data enrichment step
├── event_labelling/
│   ├── CodeStructure&Branching/
│   │   └── code_structure_and_branching.py  # Code structure analysis
│   ├── Utility/                # 🆕 Utility modules
│   |   ├── botFilter.py        # 🤖 Bot filtering utility
│   ├── csvFix.py           # CSV repair utilities
│   ├── pr_communication_label.py  # PR communication labeling
│   └── relabelling.py      # Data relabeling utilities
├── process_model/
│   ├── clean.py                # Data cleaning
│   ├── preprocessing.py        # Data preprocessing
│   └── graphing.py             # Graph generation
├── test/
│   ├── testApp.py              # App testing
│   ├── testBot_filter.py       # 🆕 Bot filter tests
│   └── testClean.py            # Clean module tests
├── data/
│   └── csv/                    # Output CSVs and processed data
├── confidential/               # Sensitive or anonymized data (e.g., usernames)
└── README.md                   # This file
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