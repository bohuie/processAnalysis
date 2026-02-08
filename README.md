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

Create a `.env` file (or edit the existing one) at the repo root. Here's what you need:

```bash
# ============================================
# REQUIRED
# ============================================
GITHUB_TOKEN=ghp_your_github_token_here

# ============================================
# OPTIONAL: AI Backend (for LLM labeling)
# ============================================
# Choose: 'offline' (local Ollama) or 'online' (Groq Cloud)
# Default: offline (no API costs, works without internet)
AI_MODE=offline

# Only needed if AI_MODE=online
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL_NAME=llama-3.1-8b-instant  # optional
```

**Key Points:**
- `GITHUB_TOKEN` is **required** for data extraction
- `AI_MODE` controls which LLM backend to use
- Everything else is automatic

---

### LLM Setup and AI_MODE Toggle

This project uses an **LLM for analyzing code structure and PR communications**. You can choose between:

- **Offline mode** (AI_MODE=offline): Uses local Ollama with `llama3.2:3b`
- **Online mode** (AI_MODE=online): Uses Groq Cloud API for faster processing

#### Choose Your Mode

Set `AI_MODE` in your `.env` file:

```bash
# .env file
AI_MODE=offline    # Use local Ollama (default, no API key needed)
# OR
AI_MODE=online     # Use Groq Cloud API (requires GROQ_API_KEY)
```

#### Option 1: Offline Mode (AI_MODE=offline) — Local Ollama

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

#### Option 2: Online Mode (AI_MODE=online) — Groq Cloud API

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

#### Where AI_MODE is Used

The `AI_MODE` toggle is used in:
- **Event Labelling → CodeStructure_Branching**: When running `python -m event_labelling.CodeStructure_Branching.main`
  - Uses LLM to analyze branch names and PR structure
  - Outputs labeled CSVs to `data/graph_labels/clean/`

---

## Architecture & How It Works

### Data Flow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Data Extraction (GitHub API)                             │
│ scripts/app.py → Fetch PR metadata, commits, reviews            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Output: data/csv/year-long-project-team-*/
                       ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2a: Branching Analysis (LLM)                               │
│ event_labelling/CodeStructure_Branching/main.py                 │
│ → Label branch patterns, feature sizes, refactoring             │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Output: data/graph_labels/clean/
                       ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2b: PR Communications Analysis (LLM)                       │
│ event_labelling/PR/pr_label.py                                  │
│ → Analyze reviews, descriptions, communication patterns         │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Output: data/csv/CLEAN_pr_labels_*.csv
         ┌─────────────┴─────────────┐
         ↓                           ↓
    BRANCHING DATA            PR LABELS DATA
    (analyzed separately)     (analyzed separately)
    
         ↓                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Process Model Analysis (BOTH DATASETS)                  │
│ Runs 4 substeps for branching AND pr_labels automatically       │
│                                                                 │
│ 3.1: transition_edges.py   → Build state transitions            │
│ 3.2: zscore_calculation.py → Normalize counts                   │
│ 3.3: clustering.py         → Find similar teams                 │
│ 3.4: graphing.py           → Visualize patterns                 │
└──────────────────────┬──────────────────────────────────────────┘
         ┌─────────────┴─────────────┐
         ↓                           ↓
    data/outputs/              data/outputs/
    branching/                 pr/
```

### What Each Step Does

1. **Data Extraction** — Fetches raw PR data from GitHub
2. **Branching Labeling** — Uses LLM to categorize branch strategies and code patterns
3. **PR Labeling** — Uses LLM to analyze communication quality and review patterns
4. **Process Modeling** — Analyzes workflow transitions for both datasets:
   - Builds Markov chains: which events follow which
   - Normalizes to find anomalies (z-scores)
   - Clusters teams by similarity
   - Visualizes patterns as graphs


### 5. Run the Pipeline (main.py)

The project provides a complete end-to-end pipeline with **zero environment variable configuration needed** (except `GITHUB_TOKEN` and `AI_MODE`).

#### Run Everything at Once

```bash
# Just run main.py - it handles everything!
python main.py
```

That's it. `main.py` automatically:
1. ✅ Extracts PR data from repositories
2. ✅ Labels branching patterns and code structure
3. ✅ Labels PR communications and review patterns
4. ✅ **Processes BOTH branching AND pr_labels datasets simultaneously**
5. ✅ Generates graphs and analysis for both datasets

**Output locations:**
- Branching analysis: `data/outputs/branching/`
- PR analysis: `data/outputs/pr/`

#### The Modular Way: Run Steps Individually

If you prefer to run steps separately:

#### Step 1: Data Extraction
```bash
python scripts/app.py
```
**What it does:** Fetches PR metadata, commits, comments from GitHub repos
**Output:** `data/csv/year-long-project-team-*/`

#### Step 2a: Code Structure & Branching Analysis
```bash
python -m event_labelling.CodeStructure_Branching.main
```
**What it does:** Uses LLM (Ollama or Groq) to label branch names, feature sizes, refactoring patterns
**Output:** `data/graph_labels/clean/CLEAN_*_branching_and_structure.csv`

#### Step 2b: PR Communications Analysis
```bash
python -m event_labelling.PR.pr_label
```
**What it does:** Analyzes PR descriptions, reviews, and communication patterns
**Output:** `data/csv/pr_communications_labels_*.csv` + `data/csv/CLEAN_pr_labels_*.csv`

#### Step 3: Process Model Analysis (Automatic for Both Datasets)
```bash
# Run the 4-step pipeline - it processes both branching AND pr_labels automatically
python -m process_model.transition_edges      # Compute state transitions
python -m process_model.zscore_calculation    # Normalize transition counts
python -m process_model.clustering            # Identify behavior clusters
python -m process_model.graphing              # Generate visualization graphs
```

**What it does:** 
- Analyzes workflow patterns (state transitions between PR events)
- Computes z-scores to identify anomalies
- Clusters teams by similar behaviors
- Generates Graphviz visualizations

**Output locations:**
- `data/outputs/branching/` - branching-based analysis
- `data/outputs/pr/` - PR-communication-based analysis

Each directory contains:
- `team_transition_edges_overall.csv` - All transitions (aggregated)
- `team_transition_edges_avg_session.csv` - Averaged per PR session
- `team_transition_edges_avg_session_zscores.csv` - Normalized scores
- `behavior_clusters_[branching|pr].csv` - Cluster assignments
- `graphs/` - PNG visualizations per team and cluster

---


## Environment Variables Reference

This is the **complete list** of all environment variables used by the project. Keep this in your `.env` file at the repo root.

### Required Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `GITHUB_TOKEN` | GitHub API authentication for data extraction | `ghp_xxxxxxxxxxxxxxxxxxxx` |

### AI Backend Variables

| Variable | Purpose | Values | Default |
|----------|---------|--------|---------|
| `AI_MODE` | Choose LLM backend | `offline` (Ollama) or `online` (Groq) | `offline` |
| `GROQ_API_KEY` | Groq Cloud API key (only needed if `AI_MODE=online`) | API key from console.groq.com | (empty) |
| `GROQ_MODEL_NAME` | Which Groq model to use | `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, etc. | `llama-3.1-8b-instant` |



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
│   │   └── clean_lables.py             # Optional PR-level-only cleaner
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


## Troubleshooting

### "No teams found" during extraction
```bash
# Check if repositories exist
python -c "from src.utils.list_repos import get_org_repositories; \
print(get_org_repositories('COSC-499-W2023'))"

# Verify GITHUB_TOKEN is set correctly
echo $GITHUB_TOKEN
```

### "LLM inference failed" during labeling
```bash
# If using offline mode, check Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve &

# Verify model exists
ollama list
```

### "Missing input files" during process_model
```bash
# Make sure you ran the labeling step first
python -m event_labelling.CodeStructure_Branching.main
python -m event_labelling.PR.pr_label

# Then run process_model
python -m process_model.transition_edges
```

### Outputs are incomplete
- Check `data/outputs/branching/` and `data/outputs/pr/` both have files
- Both should be populated after running main.py
- If one is missing, check the console output for errors

---

## Notes

- **GitHub API Token:** Required for data collection. Set as `GITHUB_TOKEN` environment variable.
- **Bot Filtering:** Automatically applied during data processing. Customize patterns in `botFilter.py` if needed.
- **Anonymization:** Update paths in scripts if using anonymized datasets.
- **Working Directory:** All scripts assume execution from the project root directory.
- **Ollama Dependency:** Code structure analysis requires a running Ollama server (or Groq API key).

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