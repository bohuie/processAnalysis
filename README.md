# Collaboration Analysis – Replication Package

This repository provides a complete pipeline for analyzing collaboration and code structure patterns in GitHub repositories.  
It uses the **GitHub API** and **LLM-based analysis (Ollama 3.2:3B by default, Groq optional)** to extract, enrich, clean, and visualize repository pull request (PR) and code structure data.

---

## Overview

The workflow consists of several stages — from data extraction to graph generation and statistical analysis.

### Main Features

- **Data Extraction:** Automatically pulls PR and repository metadata via GitHub API.
- **Data Enrichment:** Enhances raw PR data with communication and structure insights.
- **Data Cleaning & Preprocessing:** Standardizes data for analysis.
- **Bot Filtering:** Removes automated bot accounts from analysis.
- **Graph Generation:** Visualizes PR networks, branching behavior, and collaboration patterns.
- **Statistical Analysis:** Provides summary statistics of repository activity.

---

## Setup Instructions

### Prerequisites

- Python 3.9+ installed (check with `python --version`)
- Git installed (check with `git --version`)
- A GitHub Personal Access Token (classic or fine-grained) with `repo` scope, exported as `GITHUB_TOKEN`
- Optional but recommended: `make` or just use the shell commands below
- Optional (for Code Structure & Branching LLM labels): Ollama installed and model `llama3.2:3b` pulled

### Quickstart (happy path)

```bash
git clone https://github.com/<your-username>/processAnalysis.git
cd processAnalysis
```

### How to Set Up GROQ API Key

1. Log in or create a Groq account:

- https://console.groq.com/login

2. Create an API key:

- https://console.groq.com/keys

3. Add the following to your .env file in the project root (do not include the <>):

```bash
GROQ_API_KEY=<your-groq-api-key>
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

Create a `.env` file (or edit the existing one) at the repo root. Here's a complete example:

```bash
# ============================================
# GITHUB API (REQUIRED)
# ============================================
GITHUB_TOKEN=ghp_your_github_token_here

# ============================================
# AI BACKEND (for Code Structure/PR labeling)
# ============================================
# Choose AI_MODE: 'offline' (local Ollama) or 'online' (Groq API)
AI_MODE=offline

# Only needed if AI_MODE=online
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL_NAME=llama-3.1-8b-instant  # optional, defaults to this

# ============================================
# PROCESS MODEL TOGGLE (for graphing pipeline)
# ============================================
# IMPORTANT: FILE_SOURCE and FOLDER_SOURCE must be paired correctly!
# Option A: Branching/Structure analysis
FILE_SOURCE=branching
FOLDER_SOURCE=branching

# Option B: PR-label analysis (comment out Option A if using this)
# FILE_SOURCE=pr_labels
# FOLDER_SOURCE=pr
```

**Key Points:**

- `GITHUB_TOKEN` is **required** for data extraction
- `AI_MODE` determines which LLM backend to use (see [LLM Setup](#-llm-setup--ai_mode-toggle) section)
- `FILE_SOURCE` and `FOLDER_SOURCE` work together (see [Process Model Generation](#-process-model-generation-toggle-system) section)
- You can only have ONE set of FILE_SOURCE/FOLDER_SOURCE active at a time

---

## LLM Setup and AI_MODE Toggle

This project uses an **LLM for analyzing code structure and PR communications**. You can choose between:

- **Offline mode** (AI_MODE=offline): Uses local Ollama with `llama3.2:3b`
- **Online mode** (AI_MODE=online): Uses Groq Cloud API for faster processing

### Choose Your Mode

Set `AI_MODE` in your `.env` file:

```bash
# .env file
AI_MODE=offline    # Use local Ollama (default, no API key needed)
# OR
AI_MODE=online     # Use Groq Cloud API (requires GROQ_API_KEY)
```

### Option 1: Offline Mode (AI_MODE=offline) — Local Ollama

**Advantages:** No API costs, works without internet, privacy-friendly
**Requirements:** More local compute, slower than Groq

**Setup steps:**

1. **Install Ollama** from [ollama.com/download](https://ollama.com/download)

2. **Pull the model:**

   ```bash
   ollama pull llama3.2:3b
   ```

3. **Start the Ollama server** (keep running in background):

   ```bash
   ollama serve
   ```

   The server will listen on `http://localhost:11434` by default.

4. **Set in .env:**
   ```bash
   AI_MODE=offline
   ```

### Option 2: Online Mode (AI_MODE=online) — Groq Cloud API

**Advantages:** Faster processing, lower local resource usage
**Requirements:** Groq API key, internet connection, may have API costs

**Setup steps:**

1. **Create a Groq account** at [console.groq.com](https://console.groq.com)

2. **Generate an API key:**
   - Go to [console.groq.com/keys](https://console.groq.com/keys)
   - Click "Create API Key"
   - Copy the key

3. **Add to .env:**
   ```bash
   AI_MODE=online
   GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   GROQ_MODEL_NAME=llama-3.1-8b-instant  # optional, this is the default
   ```

### Where AI_MODE is Used

The `AI_MODE` toggle is used in:

- **Event Labelling → CodeStructure_Branching**: When running `python -m event_labelling.CodeStructure_Branching.main`
  - Uses LLM to analyze branch names and PR structure
  - Outputs labeled CSVs to `data/graph_labels/clean/`

---

## How to Run

Below is the **recommended execution order**:

### 1. Data Collection

Run `app.py` to pull data for selected repositories.

```bash
python scripts/app.py
```

NOTE: Before running, open [scripts/app.py](scripts/app.py) and set:

- `REPO_OWNER` (string)
- `ORG_NAME` (string or empty)
- `REPOSITORIES` (list of repo names)

### 2. Labeling

Run from the repo root after extraction:

```bash
# PR labeling
python -m event_labelling.PR.pr_label

# Code Structure and Branching labeling
python -m event_labelling.CodeStructure_Branching.main
```

Outputs land in `data/csv/<team>/...` (same folders generated by app.py). If files are missing, the scripts skip that team with a warning.

### 3. Process Model Generation (Toggle System)

** Critical:** The process model pipeline uses **two paired environment variables** that control which dataset to process. You can only run **one mode at a time** (branching OR pr_labels).

#### Understanding the Toggle System

Two environment variables work together to switch between dataset sources:

| Variable        | Purpose                                                                            | Possible Values            |
| --------------- | ---------------------------------------------------------------------------------- | -------------------------- |
| `FILE_SOURCE`   | Controls which **input files** are read (used by `transition_edges.py`)            | `branching` or `pr_labels` |
| `FOLDER_SOURCE` | Controls which **output folder** is used (used by all other process_model scripts) | `branching` or `pr`        |

**Critical Rule:** `FILE_SOURCE` and `FOLDER_SOURCE` must be paired correctly:

- If `FILE_SOURCE=branching` → must have `FOLDER_SOURCE=branching`
- If `FILE_SOURCE=pr_labels` → must have `FOLDER_SOURCE=pr`

#### How the Toggle Works

**FILE_SOURCE determines the data source:**

- `FILE_SOURCE=branching`: reads from `data/graph_labels/clean/CLEAN_year-long-project-team-*_labels_branching_and_structure.csv`
- `FILE_SOURCE=pr_labels`: reads from `data/csv/CLEAN_pr_labels_year-long-project-team-*.csv`

**FOLDER_SOURCE determines the output location:**

- `FOLDER_SOURCE=branching`: writes to and reads from `data/outputs/branching/`
- `FOLDER_SOURCE=pr`: writes to and reads from `data/outputs/pr/`

#### Running the Pipeline

**Mode 1: Generate Branching/Structure Process Models**

```bash
# Update .env file
echo "FILE_SOURCE=branching" >> .env
echo "FOLDER_SOURCE=branching" >> .env

# Or set them directly in terminal
export FILE_SOURCE=branching
export FOLDER_SOURCE=branching

# Run the 4-step pipeline in order (do NOT skip steps)
python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

**Mode 2: Generate PR-Label Process Models**

```bash
# Update .env file
echo "FILE_SOURCE=pr_labels" >> .env
echo "FOLDER_SOURCE=pr" >> .env

# Or set them directly in terminal
export FILE_SOURCE=pr_labels
export FOLDER_SOURCE=pr

# Run the 4-step pipeline in order (do NOT skip steps)
python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

**Important Notes:**

- Run the 4 scripts in the exact order shown (transition_edges → zscore_calculation → clustering → graphing)
- Do NOT mix modes in a single run (all 4 scripts must use the same FILE_SOURCE + FOLDER_SOURCE pair)
- Output graphs and CSVs are saved to `data/outputs/{branching|pr}/`
- If you switch modes, the previous mode's outputs remain in their respective folder

### 6. Statistical Analysis (Optional)

To get general repository statistics run the project-level analysis script from the repo root:

```bash
python -m analysis
```

---

## Quick Reference: Common Tasks

### "I haven't run anything yet" — Complete Setup & First Run

```bash
# 1. Set up environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Create .env with your GitHub token
echo "GITHUB_TOKEN=ghp_your_token" > .env
echo "AI_MODE=offline" >> .env

# 3. (Optional) Start Ollama if using offline mode
ollama serve &

# 4. Extract data
python scripts/app.py

# 5. Label the data
python -m event_labelling.PR.pr_label
python -m event_labelling.CodeStructure_Branching.main

# 6. (Optional) Generate process models
echo "FILE_SOURCE=branching" >> .env
echo "FOLDER_SOURCE=branching" >> .env
python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

### "I want to switch from Ollama to Groq" — Enable Online Mode

```bash
# 1. Get your Groq API key from console.groq.com/keys
# 2. Update .env
echo "AI_MODE=online" > .env
echo "GROQ_API_KEY=gsk_xxxx" >> .env

# 3. Re-run labeling scripts
python -m event_labelling.CodeStructure_Branching.main
```

### "I want to switch from Branching to PR analysis" — Toggle Process Models

```bash
# 1. Update .env
echo "FILE_SOURCE=pr_labels" > .env
echo "FOLDER_SOURCE=pr" >> .env

# 2. Re-run the entire 4-step pipeline
python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

### "My Ollama server isn't working" — Debug

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Check if model is installed
ollama list

# If not, pull it
ollama pull llama3.2:3b
```

---

## Environment Variables Reference

This is the **complete list** of all environment variables used by the project. Keep this in your `.env` file at the repo root.

### Required Variables

| Variable       | Purpose                                       | Example                    |
| -------------- | --------------------------------------------- | -------------------------- |
| `GITHUB_TOKEN` | GitHub API authentication for data extraction | `ghp_xxxxxxxxxxxxxxxxxxxx` |

### AI Backend Variables

| Variable          | Purpose                                              | Values                                             | Default                |
| ----------------- | ---------------------------------------------------- | -------------------------------------------------- | ---------------------- |
| `AI_MODE`         | Choose LLM backend                                   | `offline` (Ollama) or `online` (Groq)              | `offline`              |
| `GROQ_API_KEY`    | Groq Cloud API key (only needed if `AI_MODE=online`) | API key from console.groq.com                      | (empty)                |
| `GROQ_MODEL_NAME` | Which Groq model to use                              | `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, etc. | `llama-3.1-8b-instant` |

### Process Model Variables (Must be paired)

| Variable        | Purpose                                     | Options                    | Pairing Rule               |
| --------------- | ------------------------------------------- | -------------------------- | -------------------------- |
| `FILE_SOURCE`   | Input data source for `transition_edges.py` | `branching` or `pr_labels` | Must match `FOLDER_SOURCE` |
| `FOLDER_SOURCE` | Output folder for all process_model scripts | `branching` or `pr`        | Must match `FILE_SOURCE`   |

**Pairing Examples:**

```bash
# Valid: Branching mode
FILE_SOURCE=branching
FOLDER_SOURCE=branching

# Valid: PR mode
FILE_SOURCE=pr_labels
FOLDER_SOURCE=pr

# INVALID: Mismatched (don't do this!)
FILE_SOURCE=branching
FOLDER_SOURCE=pr  # INVALID - Don't do this!
```

---

## Utility Modules

### Bot Filter (`src/utils/botFilter.py`)

A reusable utility module for identifying and removing automated bot accounts from GitHub data. This utility is critical for ensuring analysis metrics reflect genuine human collaboration, not bot activity.

**What It Does:**

- Detects common bot patterns (dependabot, renovate, GitHub Actions, Codecov, etc.)
- Removes bot accounts from any DataFrame column containing usernames
- Works with multiple username columns (author, reviewer, merged_by, etc.)
- Provides custom pattern support for organization-specific bots
- Logs filtering statistics for transparency

**Why You Need It:**
GitHub repos contain noise from dependency bots, CI/CD automation, and security scanners. These skew collaboration metrics. This utility filters them out so your analysis focuses on **real team activity**.

**Quick Example:**

```python
from src.utils.botFilter import remove_bot_prs, filter_bots_from_multiple_columns
import pandas as pd

# Load PR data
prs_df = pd.read_csv('data/prs.csv')  # 1500 records

# Remove bot PRs (uses 'pr_author' column)
clean_prs = remove_bot_prs(prs_df)
# Output: [INFO] Filtered out 47 bot records from 1500 total (3.1%)

# Filter multiple columns (author + reviewer)
clean_prs = filter_bots_from_multiple_columns(
    clean_prs,
    username_columns=['pr_author', 'pr_reviewer'],
    filter_mode='any'
)
# Result: 1430 human-only records ready for analysis
```

**Core Functions:**
| Function | Purpose |
|----------|---------|
| `is_bot_username(username)` | Check if single username is a bot |
| `filter_bots_from_dataframe(df, username_column)` | Remove bots from one column |
| `filter_bots_from_multiple_columns(df, columns)` | Remove bots from multiple columns |
| `get_bot_usernames(df, username_column)` | List all detected bots |
| `remove_bot_prs(df)` | Shortcut for PR data |
| `remove_bot_commits(df)` | Shortcut for commit data |

**For Detailed Information:**
See [documentation/bot_filter.md](documentation/bot_filter.md) for:

- Complete API reference
- Real-world workflow examples
- Custom pattern configuration
- Troubleshooting guide
- Performance notes

---

## Output

The scripts produce:

- **Cleaned CSV files** with enriched PR and code structure data.
- **Graph visualizations** showing collaboration patterns, code structure networks, and branching metrics.
- **Summary statistics** in CSV or plotted form.
- **Bot-filtered datasets** for accurate human collaboration analysis.

---

## Project Structure (Key Files)

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
│   │   ├── label_repo_status.py
│   │   ├── label_pr_status.py
│   │   └── clean_labels.py             # Optional PR-level-only cleaner
│   ├── PR/
│   │   ├── pr_label.py
│   │   ├── helpers_pr.py
│   │   ├── prep_data.py
│   │   ├── get_clean_pr_label.py
│   │   ├── llm_prompts.py
│   │   └── review_helper.py
│   └── Communication/
│       └── comm_label.py
├── process_model/
│   ├── preprocessing.py
│   └── graphing.py
├── test/
│   ├── test_llm_output.py
│   ├── testApp.py
│   └── testBot_filter.py
├── data/
│   └── csv/                           # Output CSVs and processed data (per-team folders from app.py)
├── confidential/                      # Optional: anonymization mapping, secrets (gitignored)
└── requirements.stable.txt
```

---

## Configuration

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

## Notes

- **GitHub API Token:** Required for data collection. Set as `GITHUB_TOKEN` environment variable.
- **Bot Filtering:** Automatically applied during data processing. Customize patterns in `botFilter.py` if needed.
- **Anonymization:** Update paths in scripts if using anonymized datasets.
- **Working Directory:** All scripts assume execution from the project root directory.
- **Ollama Dependency:** Code structure analysis requires a running Ollama server.

---

## Testing

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

## Planned Integration Pipeline with collabAnalysis

To avoid duplicate GitHub data extraction across repositories, the long-term
architecture will centralize data pulling inside `processAnalysis`.

The intended workflow is:

1. `processAnalysis` pulls GitHub repository data using the GitHub API.
2. The extracted data is normalized and stored as intermediate artifacts
   (e.g., CSV/JSON files).
3. The `processAnalysis` pipeline consumes this data to generate:
   - PR process graphs
   - branching pattern graphs
   - clustering and transition statistics
4. `collabAnalysis` will also consume the same intermediate dataset to
   generate collaboration reports and PDF summaries.

This design ensures that GitHub data is extracted once and reused across
both analysis pipelines.

### High-Level Pipeline

GitHub API  
 ↓  
processAnalysis data extraction  
 ↓  
Normalized intermediate dataset  
 ├─> processAnalysis modeling + graphs  
 └─> collabAnalysis reporting + PDF generation

---
