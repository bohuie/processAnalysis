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
- 📊 **Graph Generation:** Visualizes PR networks, branching behavior, and collaboration patterns.
- 📈 **Statistical Analysis:** Provides summary statistics of repository activity.

---

## ⚙️ Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/collabAnalysis.git
cd collabAnalysis
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate    # (Mac/Linux)
venv\Scripts\activate       # (Windows)
```

### 3. Install Dependencies
Install Python dependencies listed in `requirements.txt` (if not present, manually include your project’s libraries such as `pandas`, `requests`, `tqdm`, `ollama`, etc.):
```bash
pip install -r requirements.txt
```

---

## 🤖 Ollama Setup

This project uses **Ollama 3.2:3B** for analyzing PR communications and code structure.

### 1. Install Ollama
Follow instructions from [Ollama’s official site](https://ollama.com/download).

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

1. **Data Collection**  
   Run `app.py` to pull data for selected repositories.
   ```bash
   python scripts/app.py
   ```
   ⚠️ Make sure you’ve added your target repositories in the `repositories` list before running.

2. **Data Enrichment**  
   ```bash
   python enrich_output/overwrite_files.py
   python process_model/pr_communication_label.py
   ```

3. **Code Structure & Branching Analysis**  
   Requires a running Ollama instance.
   ```bash
   python process_model/event_labelling/code_structure_and_branching.py
   python process_model/event_labelling/csvFix.py
   ```

4. **Data Cleaning**  
   ```bash
   python process_model/clean.py
   ```

5. **Preprocessing (for Graphs)**  
   Keep only one section active if working with split datasets.
   ```bash
   python process_model/preprocessing.py
   ```

6. **Graph Generation**  
   ```bash
   python process_model/graphing.py
   ```

7. **Statistical Analysis (Optional)**  
   To get general repository statistics:
   ```bash
   python process_model/event_labeling/analysis.py
   ```

---

## 📊 Output

The scripts produce:
- **Cleaned CSV files** with enriched PR and code structure data.
- **Graph visualizations** showing collaboration patterns, code structure networks, and branching metrics.
- **Summary statistics** in CSV or plotted form.

---

## 🧱 Project Structure

```
collabAnalysis/
├── scripts/
│   └── app.py                  # Fetches data via GitHub API
├── enrich_output/
│   └── overwrite_files.py      # Data enrichment step
├── process_model/
│   ├── pr_communication_label.py
│   ├── code_structure_and_branching.py
│   ├── clean.py
│   ├── preprocessing.py
│   ├── graphing.py
│   └── event_labeling/
│       └── analysis.py
├── data/
│   └── csv/                    # Output CSVs and processed data
├── confidential/               # Sensitive or anonymized data (e.g., usernames)
└── README.md                   # This file
```

---

## 🧩 Notes
- You may need a valid **GitHub API token** set as an environment variable (`GITHUB_TOKEN`).
- If anonymized data is used, update paths in the scripts accordingly.
- All scripts assume the working directory is the project root.
- You will need to the selected Repository to the varaible called **REPOSITORIES** and organizational variable values **REPO_OWNER** and **ORG_NAME**