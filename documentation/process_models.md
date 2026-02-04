# Process Models — Transition Edges, Z-Scores, Clustering, Graphing

This document describes the **process-model pipeline** in `process_model/`, which converts “clean” event streams into **Markov transition edges**, normalizes them via **per-team z-scores**, clusters teams into **behavior groups**, and renders **Markov graphs** as PNGs.

Run order (required):

1. `python -m process_model.transition_edges`
2. `python -m process_model.zscore_calculation`
3. `python -m process_model.clustering`
4. `python -m process_model.graphing`

Core scripts:

- `transition_edges.py`
- `zscore_calculation.py`
- `clustering.py`
- `graphing.py`

---

## Overview & Purpose

The goal is to build a **team-level behavioral process model** from event sequences (PR labels or branching/structure labels). The pipeline answers questions like:

- What event transitions are most common (overall vs per-session average)?
- Which transitions are **unusually strong** for a team (z-score filtering)?
- Do teams cluster into distinct behavioral “types” based on their transition patterns?
- What do the resulting Markov graphs look like per team and per cluster?

---

## Key Dependencies / Requirements

Python packages used across the pipeline:

- `pandas`, `numpy`
- `python-dotenv` (loads `.env`)
- `scikit-learn` (KMeans, silhouette score)
- `networkx`, `graphviz` (graph rendering)

System requirement:

- **Graphviz installed** (for `dot.render(...)` to produce PNGs). `graphviz` Python package alone is not enough if the system binary is missing.

---

## Configuration: `FILE_SOURCE` vs `FOLDER_SOURCE`

This pipeline uses two environment variables (loaded from your repo root `.env`):

### `FILE_SOURCE` (used by `transition_edges.py`)

Determines **which clean label files** are used as input.

- `FILE_SOURCE=branching`
  Reads: `data/graph_labels/clean/CLEAN_year-long-project-team-*_labels_branching_and_structure.csv`
  Writes outputs to: `data/outputs/branching/`

- `FILE_SOURCE=pr_labels`
  Reads: `data/csv/CLEAN_pr_labels_year-long-project-team-*.csv`
  Writes outputs to: `data/outputs/pr/`

### `FOLDER_SOURCE` (used by `zscore_calculation.py`, `clustering.py`, `graphing.py`)

Determines **which outputs folder** downstream scripts read from and write to:

- `FOLDER_SOURCE=branching` → `data/outputs/branching/`
- `FOLDER_SOURCE=pr` → `data/outputs/pr/`

**Important pairing rule:**

- If `FILE_SOURCE=branching`, you almost always want `FOLDER_SOURCE=branching`.
- If `FILE_SOURCE=pr_labels`, you almost always want `FOLDER_SOURCE=pr`.

---

## Running the Pipeline

### Branching/Structure process models

```bash
export FILE_SOURCE=branching
export FOLDER_SOURCE=branching

python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

### PR-label process models

```bash
export FILE_SOURCE=pr_labels
export FOLDER_SOURCE=pr

python -m process_model.transition_edges
python -m process_model.zscore_calculation
python -m process_model.clustering
python -m process_model.graphing
```

---

## Stage 1 — Transition Edges (`transition_edges.py`)

**Purpose:** Convert each team’s clean event stream into:

- **Overall transition edges** (pooled counts across PR sessions; no START/END)
- **Average session edges** (START/END included; counts divided by number of sessions)
- **Event frequency table**
- **PR session count per team**

### Inputs

Depends on `FILE_SOURCE`:

#### `FILE_SOURCE=branching`

Looks in:

- `data/graph_labels/clean/`
- filenames like: `CLEAN_year-long-project-team-7_labels_branching_and_structure.csv`

#### `FILE_SOURCE=pr_labels`

Looks in:

- `data/csv/`
- filenames like: `CLEAN_pr_labels_year-long-project-team-7.csv`

**Required columns in each input file:**

- `pr_id`, `timestamp`, `event`

### Event normalization (important detail)

The script supports both:

- a single event string (e.g., `"reviewed_merge"`)
- a list-like string (e.g., `"['reviewed_merge', 'changes_requested']"`)

It normalizes to an `event_list`, then **explodes** to one event per row (old graphing behavior).

Ordering is preserved using `_row_idx`, then a stable sort by:
`pr_id`, `timestamp`, `_row_idx` — so within-timestamp ordering remains deterministic.

### Transition edge logic

Per `pr_id`, the script builds the ordered event sequence and counts transitions:

**Overall edges (old style):**

- counts transitions `event[i] -> event[i+1]`
- **no START/END**
- pooled counts across all PR sessions

**Average session edges (old style):**

- counts transitions with `START -> first_event` and `last_event -> END`
- pooled counts across sessions then divided by `n_sessions`

Then it adds transition probabilities per `from` state:
`prob = count / sum(counts from same from-state)`

### Outputs (written to `data/outputs/{branching|pr}/`)

- `team_transition_edges_overall.csv` (includes `from,to,count,prob`)
- `team_transition_edges_avg_session.csv` (includes `from,to,count,prob`; START/END expected)
- `team_transition_sessions_count.csv` (team → `num_pr_sessions`)
- `team_event_frequency.csv` (counts of each event per team)

---

## Stage 2 — Z-Score Normalization (`zscore_calculation.py`)

**Purpose:** Normalize transition strengths per team by computing a **z-score over edge counts**, team-by-team. This enables later thresholding (“keep only unusually strong edges”).

### Input

Reads:

- `data/outputs/{branching|pr}/team_transition_edges_avg_session.csv`

Requires columns:

- `from`, `to`, `count`, and a team identifier column (`team_number` or `team_name`)

### Z-score rule

For each team group, with `count` treated as float:

- `z_score = (count - mean) / std` using **population std** (`ddof=0`)
- if `std == 0` (or effectively 0 / NaN), set all `z_score = 0.0` for that team

### Output

Writes:

- `data/outputs/{branching|pr}/team_transition_edges_avg_session_zscores.csv`

---

## Stage 3 — Behavior Clustering (`clustering.py`)

**Purpose:** Turn z-scored edges into a team-feature matrix and cluster teams using KMeans.

### Input

Reads:

- `data/outputs/{branching|pr}/team_transition_edges_avg_session_zscores.csv`

### Feature construction

1. Build a stable vocabulary from the **full** dataset:
   - features are all unique `(from,to)` pairs

2. Apply a z-score threshold filter:
   - keep only edges where `z_score >= Z_THRESHOLD`
     Default: `Z_THRESHOLD = 1.645` (≈ 95th percentile if normal-ish)

3. For each team, fill feature vector `X[team, pair] = count` for remaining edges.
4. Drop teams whose vectors are all zeros after thresholding.

### Choosing K (silhouette search)

- Tries `k` from 2 to min(10, n_teams-1)
- Uses `silhouette_score` to pick best `k`
- If too few teams (`n < 3`), falls back to `k=2` (or returns a trivial cluster assignment if X is too small).

### Output

Writes:

- `data/outputs/{branching|pr}/behavior_clusters_{branching|pr}.csv`

Columns include:

- `team_number`
- `cluster_id` (0-indexed)
- `k_used`
- `silhouette` (best silhouette score found, or NaN)

---

## Stage 4 — Graph Rendering (`graphing.py`)

**Purpose:** Render **per-team** and **per-cluster** Markov graphs as PNGs using Graphviz.

### Inputs (from `data/outputs/{branching|pr}/`)

Required:

- `team_transition_edges_overall.csv`
- `team_transition_edges_avg_session.csv`

### Optional / Enhancing

- `team_event_frequency.csv` (used to display node counts)
- `team_transition_sessions_count.csv` (used for session-weighted cluster averages)
- `behavior_clusters_{branching|pr}.csv` (cluster graphs; if missing, clusters are skipped)

If any of these files are missing, the script degrades gracefully and skips the corresponding enhancements.

### Configuration (Environment Variables)

| Variable            | Default        | Description                                                                                                                |
| :------------------ | :------------- | :------------------------------------------------------------------------------------------------------------------------- |
| `GRAPH_ORIENTATION` | `horizontal`   | `vertical` for Top-to-Bottom, `horizontal` for Left-to-Right.                                                              |
| `GRAPH_SIZE`        | `12,6` (horiz) | Custom Graphviz size string (e.g., `"8,5"`).                                                                               |
| MIN_EDGE_PROB       | 0.0            | Hides edges in the **visual** PNG output below this probability. Does **not** affect clustering or underlying data models. |

### Team graph outputs

For each team, the script writes PNGs into:

```
data/outputs/{branching|pr}/year-long-project-team-{team_number}/
├── team_overall/
│   └── team{N}_overall.png
└── team_avg_session/
    └── team{N}_avg_session.png
```

This is done by:

- building a directed graph from `from,to,count`
- converting counts into transition probabilities (per “from” node)
- drawing nodes; `START` and `END` get special styling; other nodes show event count if available.

**Edge filtering:** transitions with `prob < MIN_EDGE_PROB` are omitted from the graph to keep it readable (this is a visual-only filter).

### Cluster graph outputs (optional)

If cluster CSV exists and has `team_number, cluster_id`, the script aggregates **avg-session edges** per cluster using session-weighting:

- `cluster_total_counts = sum(team_avg_count * team_num_sessions)`
- `cluster_avg = cluster_total_counts / sum(team_num_sessions)`

Then writes:

```
data/outputs/{branching|pr}/clusters/
└── cluster{human_cluster_id}/
    └── cluster_avg_session.png
```

Note: cluster folders are named `cluster1`, `cluster2`, … (human-friendly), while `cluster_id` in CSV is 0-indexed.

---

## Common Debugging Scenarios

| Symptom                                                             | Likely Cause                                                      | Fix                                                                                                  |
| ------------------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `No CLEAN label CSVs found...` in transition step                   | `FILE_SOURCE` points to the wrong dataset or files aren’t present | Set `FILE_SOURCE=branching` or `FILE_SOURCE=pr_labels` to match where your CLEAN files actually are. |
| `Missing required input: ... team_transition_edges_avg_session.csv` | Skipped Stage 1 or wrong `FOLDER_SOURCE`                          | Run `transition_edges` first and ensure `FOLDER_SOURCE` matches the output folder.                   |
| Clustering drops many teams as all-zero                             | `Z_THRESHOLD` too high for the dataset                            | Lower `Z_THRESHOLD` in `clustering.py` (currently 1.645).                                            |
| Cluster graphs are skipped                                          | Cluster CSV missing or wrong columns                              | Ensure `behavior_clusters_{suffix}.csv` exists and contains `team_number, cluster_id`.               |
| Graph rendering fails / no PNGs produced                            | Graphviz system binary not installed                              | Install Graphviz on your OS so `dot.render(...)` can execute.                                        |

---

## File Roles Summary

- **`transition_edges.py`**: CLEAN event stream → transition edges (overall + avg-session), event frequency, session counts.
- **`zscore_calculation.py`**: avg-session edges → z-scored edges per team.
- **`clustering.py`**: z-scored edges → thresholded team vectors → KMeans clusters + silhouette-based k selection.
- **`graphing.py`**: transition edges (+ freq + sessions + clusters) → PNG Markov graphs per team and per cluster.
