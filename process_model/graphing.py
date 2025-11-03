# ============================================================
# graphing.py — Multi-team, multi-category Markov Graph Builder
# ============================================================

import os, re, glob, math, random
import pandas as pd
import numpy as np
import networkx as nx
from tqdm import tqdm
from graphviz import Digraph
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from itertools import product

# ---------- Paths ----------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
DATA_FOLDER = os.path.join(ROOT, "data", "csv")
MERGED_METADATA_FP = os.path.join(DATA_FOLDER, "merged_metadata.csv")

OUTPUTS_ROOT = os.path.join(ROOT, "data", "outputs")
CATEGORY_OUTPUTS = {
    "pr": os.path.join(OUTPUTS_ROOT, "pr"),
    "communication": os.path.join(OUTPUTS_ROOT, "communication"),
    "code-structure-branching": os.path.join(OUTPUTS_ROOT, "code-structure-branching"),
}

MERGE_EVENTS = {"self_merged", "no_merge", "reviewed_merge"}
PR_DESC_EVENTS = ["pr_description_unclear", "pr_description_clear"]

# ---------- Utilities ----------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def parse_team_number_from_path(fp: str) -> str:
    parts = fp.split(os.sep)
    for p in parts:
        if "team-" in p:
            d = re.findall(r"\d+", p)
            if d:
                return d[-1]
    d = re.findall(r"team(\d+)", os.path.basename(fp))
    return d[-1] if d else "unknown"

def clean_timestamp(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.replace('"', '', regex=False)
    s = s.str.replace("Z", "", regex=False)
    return pd.to_datetime(s, errors="coerce", utc=True)

def normalize_event_field(event):
    if isinstance(event, str) and event.startswith("["):
        try:
            parsed = eval(event)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return [event]
    return [event]

def remove_event_from_lists(ev_list, ev_to_remove):
    return [e for e in ev_list if e != ev_to_remove]

# ---------- Pre-processing: enforce merge before END ----------
def enforce_merge_end(df: pd.DataFrame, category: str) -> pd.DataFrame:
    df = df.copy()
    df["pr_id"] = df["pr_id"].fillna(0)
    out_groups = []

    # Define review-related events (so we can detect proper review flow)
    REVIEW_EVENTS = {
        "empty_review_comment",
        "changes_requested",
        "constructive_first_review",
        "constructive_additional_review",
        "non_constructive_first_review",
        "non_constructive_additional_review",
    }
    PR_DESC_EVENTS = ["pr_description_unclear", "pr_description_clear"]
    MERGE_EVENTS = {"self_merged", "no_merge", "reviewed_merge"}

    for pr_id, g in df.groupby("pr_id"):
        g = g.sort_values("created_at").copy()
        all_events_flat = sum(g["event_list"].tolist(), [])

        # --- 1. Separate Merge Rows from Base Rows ---
        # Identify rows that contain *only* a merge event (based on your structure)
        # We assume the 'event_list' column has been successfully parsed into a list of strings
        
        # Check if the list contains ANY merge event and is of length 1
        is_merge_row = g["event_list"].apply(
            lambda evs: len(evs) == 1 and evs[0] in MERGE_EVENTS
        )
        
        # Base rows: All rows that are NOT dedicated merge rows
        base = g[~is_merge_row].copy()
        
        # Merges: The actual merge events found in the data
        merges_found = set(sum(g[is_merge_row]["event_list"].tolist(), []))
        
        # --- 2. PR-only: Ensure description is earliest (Existing logic retained for completeness) ---
        if category == "pr":
            # This block handles adding/re-timing PR description events to the earliest time
            
            # Find the true earliest non-description time
            non_desc_events = [e for e in all_events_flat if e not in PR_DESC_EVENTS]
            first_ts_seed = (base["created_at"].min() if not base.empty else g["created_at"].min())
            
            descs_present = [e for e in all_events_flat if e in PR_DESC_EVENTS]
            
            if not descs_present:
                # Inject a random description if none found
                chosen = random.choice(PR_DESC_EVENTS)
                seed = (g.iloc[0]).copy() # Use original first row as seed
                seed["event_list"] = [chosen]
                seed["created_at"] = first_ts_seed - pd.Timedelta(seconds=1)
                base = pd.concat([pd.DataFrame([seed]), base], ignore_index=True)
            else:
                # Ensure all description events are consolidated and pushed to the very start
                unique_descs = list(dict.fromkeys(descs_present))
                
                # Remove description events from existing base rows
                base["event_list"] = base["event_list"].apply(
                    lambda evs: [e for e in evs if e not in PR_DESC_EVENTS]
                )
                base = base[base["event_list"].apply(len) > 0] # Drop rows that are now empty
                
                # Create new description rows at the start
                seed = g.iloc[0].copy()
                desc_rows = []
                for i, d in enumerate(unique_descs):
                    dr = seed.copy()
                    dr["event_list"] = [d]
                    dr["created_at"] = first_ts_seed - pd.Timedelta(seconds=1 + i)
                    desc_rows.append(dr)
                base = pd.concat([pd.DataFrame(desc_rows), base], ignore_index=True)


        # --- 3. Merge Handling: Identify last event and inject final merge row ---
        if category in {"pr", "communication"}:
            
            # Identify the last non-merge event for sequencing
            if not base.empty:
                # Find the row with the maximum 'created_at' in the non-merge base
                last_seed = base.loc[base["created_at"].idxmax()].copy()
                last_ts = last_seed["created_at"]
            else:
                # This PR had only merge/description events. Use the original last row as a seed.
                last_seed = g.loc[g["created_at"].idxmax()].copy()
                last_ts = last_seed["created_at"]

            # Fallback logic for merge event type (e.g., reviewed_merge -> no_merge)
            unique_merges = list(merges_found)
            if not unique_merges:
                unique_merges = ["reviewed_merge"]  # default fallback if no merge found
            
            has_review_events = any(e in all_events_flat for e in REVIEW_EVENTS)
            if not has_review_events:
                unique_merges = [
                    "no_merge" if e == "reviewed_merge" else e for e in unique_merges
                ]

            # Inject the final merge row(s)
            merge_rows = []
            for i, m in enumerate(unique_merges, start=1):
                mr = last_seed.copy()
                mr["event_list"] = [m]
                # Ensure the merge event is definitively the last one
                mr["created_at"] = last_ts + pd.Timedelta(seconds=i)
                merge_rows.append(mr)

            # Combine and ensure proper order
            result = pd.concat([base, pd.DataFrame(merge_rows)], ignore_index=True)
            result = result.sort_values("created_at").reset_index(drop=True)
        else:
            # If not PR/communication, just re-assemble the original, unsplit data
            result = base if not base.empty else g

        out_groups.append(result)

    # Final sort across PRs
    out = pd.concat(out_groups, ignore_index=True) if out_groups else pd.DataFrame(columns=df.columns)
    out = out.sort_values(["pr_id", "created_at"]).reset_index(drop=True)
    return out


# ---------- Edge and label helpers ----------
def compute_event_frequency(flat_df: pd.DataFrame) -> dict:
    return flat_df["event"].value_counts().to_dict()

def compute_edge_counts(flat_df: pd.DataFrame) -> pd.DataFrame:
    if flat_df.empty:
        return pd.DataFrame(columns=["from", "to", "count"])
    rows = []
    for sid, g in flat_df.sort_values(["session_id", "created_at"]).groupby("session_id"):
        evs = g["event"].tolist()
        for i in range(len(evs) - 1):
            rows.append((evs[i], evs[i + 1]))
    if not rows:
        return pd.DataFrame(columns=["from", "to", "count"])
    pairs = pd.DataFrame(rows, columns=["from", "to"])
    return pairs.value_counts().reset_index(name="count")

def compute_avg_session_edges(flat_df: pd.DataFrame) -> pd.DataFrame:
    if flat_df.empty:
        return pd.DataFrame(columns=["from", "to", "count"])
    edge_counter = {}
    n_sessions = 0
    for sid, g in flat_df.sort_values(["session_id", "created_at"]).groupby("session_id"):
        evs = g["event"].tolist()
        if len(evs) < 1:
            continue
        n_sessions += 1
        seq = [("START", evs[0])] + [(evs[i], evs[i + 1]) for i in range(len(evs) - 1)] + [(evs[-1], "END")]
        for a, b in seq:
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1
    rows = [{"from": a, "to": b, "count": c / n_sessions} for (a, b), c in edge_counter.items()]
    return pd.DataFrame(rows)

def apply_zscore_filter(edges, threshold, keep_merge_edges=True):
    """Apply z-score threshold filter but preserve START/END/merge-related edges."""
    if edges.empty:
        return edges.assign(z_score=[], keep=[])

    counts = edges["count"].astype(float)
    mean, std = counts.mean(), counts.std(ddof=0)

    if std == 0 or math.isclose(std, 0.0):
        edges["z_score"] = 0
        edges["keep"] = True
        return edges

    edges["z_score"] = (counts - mean) / std
    edges["keep"] = edges["z_score"] >= threshold

    if keep_merge_edges:
        merge_nodes = {"self_merged", "no_merge", "reviewed_merge"}
        edges.loc[
            edges["from"].isin(merge_nodes)
            | edges["to"].isin(merge_nodes)
            | edges["from"].isin({"START", "END"})
            | edges["to"].isin({"START", "END"}),
            "keep",
        ] = True

    return edges

def detect_auto_threshold_for_merges(edges: pd.DataFrame, candidate_thresholds=None):
    """
    Find the lowest z-threshold at which at least one merge-related edge survives.
    Checks edges involving merge nodes ('from' or 'to').
    Returns chosen_threshold (float), and summary dict.
    """
    if candidate_thresholds is None:
        # from strict to relaxed
        candidate_thresholds = [1.96, 1.645, 1.44, 1.28, 1.0, 0.5, 0.0]
    if edges.empty:
        return 0.0, {"kept_at": 0.0, "any_merge_edge": False}

    # precompute z-scores once
    ztab = apply_zscore_filter(edges.copy(), threshold=-9999.0)
    # We'll recompute "keep" per candidate threshold from the z_score column
    for thr in candidate_thresholds:
        kept = ztab[ztab["z_score"] >= thr]
        any_merge_edge = ((kept["from"].isin(MERGE_EVENTS)) | (kept["to"].isin(MERGE_EVENTS))).any()
        if any_merge_edge:
            return thr, {"kept_at": thr, "any_merge_edge": True}
    # if none satisfied, return the most relaxed threshold
    return candidate_thresholds[-1], {"kept_at": candidate_thresholds[-1], "any_merge_edge": False}

def confidence_label_from_threshold(thr: float) -> str:
    # approximate mapping
    mapping = {1.96: "≈95%", 1.645: "≈90%", 1.44: "≈85%", 1.28: "≈80%"}
    # choose closest in mapping
    closest = min(mapping.keys(), key=lambda x: abs(x - thr))
    return mapping.get(closest, f"z≥{thr:.2f}")

# ---------- Rendering ----------
def build_markov_graph(user_label, edges_df, event_freq, output_path, title_suffix="", normalize_probs=True):
    edges_df = edges_df[edges_df["count"] > 0]
    if edges_df.empty:
        print(f"[WARN] Skipping {user_label} — no edges.")
        return

    # Build directed graph with weights
    G = nx.DiGraph()
    for _, row in edges_df.iterrows():
        a, b, w = row["from"], row["to"], float(row["count"])
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
        else:
            G.add_edge(a, b, weight=w)

    # Probabilities
    for u, v in G.edges():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        G[u][v]["prob"] = G[u][v]["weight"] / total if normalize_probs and total else 0

    # Draw
    dot = Digraph(comment=f"Markov — {user_label}", format="png")
    dot.attr(rankdir="LR", size="8,5", splines="spline", nodesep="0.3", ranksep="0.3", pack="true", pad="0.2", margin="0", fontname="Helvetica")
    dot.attr("node", shape="ellipse", style="filled", fontname="Helvetica", fontsize="12", width="2.0", height="1.0")
    dot.attr("edge", color="#424242", arrowsize="0.8", fontname="Helvetica", fontsize="10",
             labelfontcolor="#000", penwidth="1.5")

    for node in G.nodes():
        if node == "START":
            dot.node(
                str(node),
                label="START",
                fillcolor="#E57373",
                color="#B71C1C",
                fontcolor="white",
                shape="circle",
                style="filled,bold",
                penwidth="2",
                width="0.8",
                height="0.8",
                fixedsize="true"
            )
        elif node == "END":
            dot.node(
                str(node),
                label="END",
                fillcolor="#81C784",
                color="#1B5E20",
                fontcolor="white",
                shape="doublecircle",
                style="filled,bold",
                penwidth="2",
                width="0.8",
                height="0.8",
                fixedsize="true"
            )
        else:
            fillcolor, fontcolor = "#90CAF9", "black"
            cnt = event_freq.get(node, 0)
            node_label = node.replace("_", "\n")
            label = f"{node_label}\n{cnt}" if cnt > 0 else node_label
            dot.node(
                str(node),
                label=label,
                fillcolor=fillcolor,
                color="#1E88E5",
                fontcolor=fontcolor,
                shape="ellipse",
                style="filled"
            )



    for u, v, data in G.edges(data=True):
        p = data.get("prob", 0.0)
        if p < 0.01:
            continue  # skip very weak transitions
        color = "#0D47A1" if p > 0.4 else "#1565C0" if p > 0.2 else "#64B5F6"
        dot.edge(str(u), str(v), label=f"{p:.2f}", color=color, penwidth=str(1.2 + p * 5))


    title = f"Markov Graph — {user_label}"
    if title_suffix:
        title += f" ({title_suffix})"
    dot.attr(label=title, labelloc="t", fontsize="14", fontname="Helvetica-Bold")
    dot.graph_attr.update(dpi="400")

    ensure_dir(os.path.dirname(output_path))
    dot.render(output_path.replace(".png", ""), cleanup=True)

# ---------- Metadata ----------
if not os.path.exists(MERGED_METADATA_FP):
    raise FileNotFoundError("merged_metadata.csv missing — run preprocessing.py first.")
meta = pd.read_csv(MERGED_METADATA_FP)
meta["team_number"] = meta["team_number"].astype(str).str.strip()
meta["anonymized_name"] = meta["anonymized_name"].fillna("").astype(str)
meta["consent_given"] = True  # assume all consented
avg_team_grade = {str(r["team_number"]): r["avg_team_grade"] for _, r in meta.iterrows()}

# ---------- Z-Score Prompt ----------
z_ans = input("Apply z-score filtering? (y/n): ").strip().lower()
if z_ans == "n":
    APPLY_Z, Z_THRESHOLD, Z_SCOPE_ALL, AUTO_Z = False, None, False, False
    print("→ Z-score filtering: disabled")
else:
    APPLY_Z = True
    print("Choose z-score confidence:")
    print("  1. 95%")
    print("  2. 90%")
    print("  3. 85%")
    print("  4. 80%")
    print("  5. Auto-set (ensure a merge state is visible)")
    choice = input("Enter 1-5: ").strip()
    conf_map = {"1": 1.96, "2": 1.645, "3": 1.44, "4": 1.28}
    if choice == "5":
        AUTO_Z = True
        Z_THRESHOLD = None
        print("→ Z-threshold: auto-set mode")
    else:
        Z_THRESHOLD = conf_map.get(choice, 1.645)
        AUTO_Z = False
        print(f"→ Z-threshold {Z_THRESHOLD} ({'≈95%' if Z_THRESHOLD==1.96 else '≈90%' if Z_THRESHOLD==1.645 else '≈85%' if Z_THRESHOLD==1.44 else '≈80%'})")
    scope = input("Apply z-score filtering to: (1) all graphs  (2) only cluster-level graphs): ").strip()
    Z_SCOPE_ALL = (scope == "1")
    print("→ Scope:", "all graphs" if Z_SCOPE_ALL else "cluster-level only")

# ---------- File Discovery ----------
pattern = os.path.join(DATA_FOLDER, "*.csv")
all_csvs = glob.glob(pattern)

teams_by_cat = {"pr": {}, "communication": {}, "code-structure-branching": {}}
for fp in all_csvs:
    base = os.path.basename(fp)
    team_num = parse_team_number_from_path(fp)
    if base.startswith("pr_labels_year-long-project-team-"):
        teams_by_cat["pr"][team_num] = fp
    elif base.startswith("communication_labels_year-long-project-team-"):
        teams_by_cat["communication"][team_num] = fp
    elif base.startswith("code_structure_branching_labels_year-long-project-team-"):
        teams_by_cat["code-structure-branching"][team_num] = fp

teams_by_cat = {k: v for k, v in teams_by_cat.items() if v}
if not teams_by_cat:
    raise FileNotFoundError(f"No input CSVs found under {pattern}")

# ---------- Processing ----------
for category, team_files in teams_by_cat.items():
    print(f"\n{'=' * 70}\n[INFO] Category: {category}\n{'=' * 70}")

    CAT_OUT = CATEGORY_OUTPUTS[category]
    ensure_dir(CAT_OUT)
    team_dfs = {}

    # -------- Per-team graphs --------
    for team, fp in sorted(team_files.items(), key=lambda x: int(re.findall(r"\d+", x[0])[0])):
        print(f"[INFO] Loading Team {team}: {fp}")
        df = pd.read_csv(fp, low_memory=False)

        required_cols = {"created_at", "event", "pr_author", "pr_id"}
        if not required_cols <= set(df.columns):
            print(f"[WARN] Skipping team {team} (missing {required_cols - set(df.columns)})")
            continue

        df["created_at"] = clean_timestamp(df["created_at"])
        df = df.dropna(subset=["created_at"]).sort_values(["pr_author", "created_at"])
        df["event_list"] = df["event"].apply(normalize_event_field)

        # enforce merge rules (PR-only injections)
        df = enforce_merge_end(df, category=category)
        
        # --- Save cleaned (post-fallback) DataFrame for debugging ---
        # cleaned_out_dir = os.path.join(CAT_OUT, f"year-long-project-team-{team}", "cleaned_csv")
        # ensure_dir(cleaned_out_dir)
        # cleaned_fp = os.path.join(cleaned_out_dir, f"cleaned_{category}_team{team}.csv")
        # df.to_csv(cleaned_fp, index=False)
        # print(f"[DEBUG] Saved cleaned fallback-adjusted CSV → {cleaned_fp}")


        # flatten rows to single events
        flat_rows = []
        for _, row in df.iterrows():
            for ev in row["event_list"]:
                flat_rows.append({
                    "team_number": str(team),
                    "pr_author": row.get("pr_author", "unknown"),
                    "created_at": row["created_at"],
                    "event": ev,
                    "pr_id": row.get("pr_id")
                })
        flat = pd.DataFrame(flat_rows)
        if flat.empty:
            continue

        # session id = team-pr
        flat["session_id"] = flat.apply(lambda r: f"{r['team_number']}-{r['pr_id']}", axis=1)
        TEAM_OUT = os.path.join(CAT_OUT, f"year-long-project-team-{team}")
        for d in ["team_overall", "team_avg_session", "individual_overall", "individual_avg_session"]:
            ensure_dir(os.path.join(TEAM_OUT, d))

        # event frequencies for node labels
        event_freq_team = compute_event_frequency(flat)

        # Team Overall
        edges = compute_edge_counts(flat)
        e_team_overall = edges.copy()
        if APPLY_Z and Z_SCOPE_ALL:
            # If Auto-Z, find threshold on team-avg edges (so merges can show)
            if AUTO_Z:
                thr, info = detect_auto_threshold_for_merges(edges)
                print(f"[INFO] Team {team}: auto z-threshold = {thr:.2f} ({confidence_label_from_threshold(thr)})")
                e_team_overall = apply_zscore_filter(edges.copy(), thr)
                e_team_overall = e_team_overall.query("keep")[["from", "to", "count"]]
            else:
                e_team_overall = apply_zscore_filter(edges.copy(), Z_THRESHOLD)
                e_team_overall = e_team_overall.query("keep")[["from", "to", "count"]]
        build_markov_graph(f"Team {team}", e_team_overall, event_freq_team,
                           os.path.join(TEAM_OUT, "team_overall", f"team{team}_overall.png"),
                           title_suffix=f"Overall • {category}")

        # Team Avg Session
        avg_edges = compute_avg_session_edges(flat)
        e_team_avg = avg_edges.copy()
        if APPLY_Z and Z_SCOPE_ALL:
            if AUTO_Z:
                thr, info = detect_auto_threshold_for_merges(avg_edges)
                print(f"[INFO] Team {team} (avg): auto z-threshold = {thr:.2f} ({confidence_label_from_threshold(thr)})")
                e_team_avg = apply_zscore_filter(avg_edges.copy(), thr)
                e_team_avg = e_team_avg.query("keep")[["from", "to", "count"]]
            else:
                e_team_avg = apply_zscore_filter(avg_edges.copy(), Z_THRESHOLD)
                e_team_avg = e_team_avg.query("keep")[["from", "to", "count"]]
        build_markov_graph(f"Team {team}", e_team_avg, event_freq_team,
                           os.path.join(TEAM_OUT, "team_avg_session", f"team{team}_avg_session.png"),
                           title_suffix=f"Avg Session • {category}")

        # Individuals
        for pr_author, g in tqdm(flat.groupby("pr_author"), desc=f"Team {team} — indiv"):
            indiv_freq = compute_event_frequency(g)

            e1 = compute_edge_counts(g)
            if APPLY_Z and Z_SCOPE_ALL:
                if AUTO_Z:
                    thr, _ = detect_auto_threshold_for_merges(e1)
                    e1 = apply_zscore_filter(e1.copy(), thr).query("keep")[["from", "to", "count"]]
                else:
                    e1 = apply_zscore_filter(e1.copy(), Z_THRESHOLD).query("keep")[["from", "to", "count"]]
            build_markov_graph(pr_author, e1, indiv_freq,
                               os.path.join(TEAM_OUT, "individual_overall", f"{pr_author}_overall.png"),
                               title_suffix=f"Overall • {category}")

            e2 = compute_avg_session_edges(g)
            if APPLY_Z and Z_SCOPE_ALL:
                if AUTO_Z:
                    thr, _ = detect_auto_threshold_for_merges(e2)
                    e2 = apply_zscore_filter(e2.copy(), thr).query("keep")[["from", "to", "count"]]
                else:
                    e2 = apply_zscore_filter(e2.copy(), Z_THRESHOLD).query("keep")[["from", "to", "count"]]
            build_markov_graph(pr_author, e2, indiv_freq,
                               os.path.join(TEAM_OUT, "individual_avg_session", f"{pr_author}_avg_session.png"),
                               title_suffix=f"Avg Session • {category}")

        team_dfs[team] = flat

    # If no teams processed, continue
    if not team_dfs:
        continue

    # ---------- Behavior-based clustering (per category) ----------
    # Build a transition vocabulary across all teams (from avg-session edges)
    all_flat = pd.concat(team_dfs.values(), ignore_index=True)
    # Per-team avg-session edges (these are what we cluster on)
    per_team_vectors = {}
    vocab_pairs = set()

    team_avg_edges = {}
    for team, fdf in team_dfs.items():
        e_avg = compute_avg_session_edges(fdf)
        team_avg_edges[team] = e_avg
        # collect vocab
        for _, r in e_avg.iterrows():
            vocab_pairs.add((r["from"], r["to"]))

    vocab_pairs = sorted(list(vocab_pairs))
    pair_to_idx = {p: i for i, p in enumerate(vocab_pairs)}

    # Optional: apply z-filter before vectorizing for clustering? We'll use same setting as cluster scope
    # Optional: apply z-filter before vectorizing for clustering? We'll use same setting as cluster scope
    def zfilter_for_cluster(edges_df: pd.DataFrame) -> pd.DataFrame:
        if not APPLY_Z:
            return edges_df
        if Z_SCOPE_ALL:
            # When scope=all, teams already filtered at the team level; for clustering we use *unfiltered* team data
            # Note: The 'flat' data in team_dfs is the *enforced* data, so Z-scores here are based on cleaned data.
            return edges_df
            
        # Scope=cluster-only: apply fixed Z_THRESHOLD for cluster computation, ignoring AUTO_Z logic here.
        # FIX: If Z_THRESHOLD is None (Auto-Z was chosen), we use a standard high confidence
        # for vector creation to enforce sparsity, NOT 0.0, which leads to the 21/1 split.
        threshold_to_apply = Z_THRESHOLD if Z_THRESHOLD is not None else 1.645
        
        # Enforce pure Z-score filter (no merge protection) for clustering vector input
        return apply_zscore_filter(edges_df.copy(), threshold_to_apply, keep_merge_edges=False)

    X_rows, teams_order = [], []
    for team in sorted(team_dfs.keys(), key=lambda x: int(re.findall(r"\d+", x)[0])):
        e_avg = team_avg_edges[team].copy()
        ztab = zfilter_for_cluster(e_avg)
        if "keep" in ztab.columns:
            kept = ztab[ztab["keep"]]
        else:
            kept = ztab
        vec = np.zeros(len(vocab_pairs), dtype=float)
        for _, r in kept.iterrows():
            idx = pair_to_idx.get((r["from"], r["to"]))
            if idx is not None:
                vec[idx] = float(r["count"])
        X_rows.append(vec)
        teams_order.append(team)

    X = np.vstack(X_rows) if X_rows else np.zeros((0, len(vocab_pairs)))
    if X.shape[0] >= 2 and X.shape[1] >= 1:
        # Determine optimal K (2..10, but not exceeding #teams)
        n_samples = X.shape[0]
        kmax = min(10, n_samples - 1)  # silhouette requires k < n_samples
        best_k, best_sil = None, -1

        for k in range(2, kmax + 1):
            if k >= n_samples:
                break

            km = KMeans(n_clusters=k, n_init=25, random_state=42)
            labels = km.fit_predict(X)
            score = silhouette_score(X, labels) if len(set(labels)) > 1 else -1
            print(score)
            if score > best_sil:
                best_sil, best_k = score, k
        if best_k is None:
            best_k = 2
        print(f"[INFO] Optimal K = {best_k} (avg silhouette = {best_sil:.4f})")
        # Final fit
        kmeans_final = KMeans(n_clusters=6, n_init=25, random_state=42)
        clusters = kmeans_final.fit_predict(X)

        # Save behavior cluster assignments & summary
        CL_OUT = os.path.join(CAT_OUT, "clusters")
        ensure_dir(CL_OUT)
        assign_df = pd.DataFrame({"team_number": teams_order, "cluster_id": clusters})
        assign_fp = os.path.join(CL_OUT, f"behavior_clusters_{category}.csv")
        assign_df.to_csv(assign_fp, index=False)
        
        # ---------- Grade-based breakdown per cluster ----------
        thr = np.nanmean([avg_team_grade.get(t) for t in teams_order])
        cluster_summary_rows = []

        for c in sorted(set(clusters)):
            cluster_teams = [t for t, lab in zip(teams_order, clusters) if lab == c]
            top_count = 0
            bot_count = 0
            cluster_grades = []

            for t in cluster_teams:
                grade = avg_team_grade.get(str(t))
                if grade is not None and not np.isnan(grade):
                    cluster_grades.append(grade)
                    if grade >= thr:
                        top_count += 1
                    else:
                        bot_count += 1

            mean_grade = np.nanmean(cluster_grades) if cluster_grades else float('nan')
            print(f"[INFO] Cluster {int(c)+1} → {len(cluster_teams)} teams "
                f"({top_count} top-half, {bot_count} bottom-half, mean grade={mean_grade:.2f}): {cluster_teams}")

            cluster_summary_rows.append({
                "category": category,
                "cluster": int(c) + 1,
                "num_teams": len(cluster_teams),
                "top_half": top_count,
                "bottom_half": bot_count,
                "mean_grade": round(mean_grade, 2),
                "teams": ", ".join(map(str, cluster_teams))
            })

        cluster_summary_df = pd.DataFrame(cluster_summary_rows)
        cluster_summary_path = os.path.join(CL_OUT, f"cluster_summary_{category}.csv")
        cluster_summary_df.to_csv(cluster_summary_path, index=False)


        # Count top/bottom halves using grades
        thr_grade = np.nanmean([avg_team_grade.get(t) for t in teams_order])
        summary_rows = []
        for c in sorted(set(clusters)):
            teams_c = [t for t, lab in zip(teams_order, clusters) if lab == c]
            num_top = sum(1 for t in teams_c if avg_team_grade.get(t, thr_grade) >= thr_grade)
            num_bot = sum(1 for t in teams_c if avg_team_grade.get(t, thr_grade) < thr_grade)
            summary_rows.append({"cluster_id": int(c), "num_teams": len(teams_c),
                                 "num_top_half": int(num_top), "num_bottom_half": int(num_bot)})
        summary_df = pd.DataFrame(summary_rows).sort_values("cluster_id")
        summary_fp = os.path.join(CL_OUT, f"cluster_summary_{category}.csv")
        summary_df.to_csv(summary_fp, index=False)

        # Global zscore summary (all edges across category, avg-session)
        all_avg_edges = compute_avg_session_edges(all_flat)
        z_global = apply_zscore_filter(all_avg_edges.copy(), threshold=-9999.0)
        z_global_fp = os.path.join(CL_OUT, f"zscore_summary_{category}.csv")
        z_global[["from", "to", "count", "z_score"]].to_csv(z_global_fp, index=False)

        # Render cluster avg-session graphs and per-cluster zscore exports
        for c in sorted(set(clusters)):
            teams_c = [t for t, lab in zip(teams_order, clusters) if lab == c]
            cdf = pd.concat([team_dfs[t] for t in teams_c])
            c_freq = compute_event_frequency(cdf)
            e2 = compute_avg_session_edges(cdf)

            # ensure cluster folder
            C_DIR = os.path.join(CL_OUT, f"cluster{int(c)+1}")
            ensure_dir(C_DIR)

            # per-cluster zscore table (unfiltered, with z)
            ztab = apply_zscore_filter(e2.copy(), threshold=-9999.0)
            ztab[["from", "to", "count", "z_score"]].to_csv(os.path.join(C_DIR, "cluster_zscores.csv"), index=False)

            # Apply cluster-level z-filter if requested (NO merge edge protection)
            e2_plot = e2.copy()
            if APPLY_Z and not Z_SCOPE_ALL:
                # FIX: Explicitly set keep_merge_edges=False here as requested
                e2_plot = apply_zscore_filter(e2.copy(), Z_THRESHOLD, keep_merge_edges=False).query("keep")[["from", "to", "count"]]

            build_markov_graph(
                user_label=f"Cluster {int(c)+1} ({category})",
                edges_df=e2_plot,
                event_freq=c_freq,
                output_path=os.path.join(C_DIR, "cluster_avg_session.png"),
                title_suffix=f"Avg Session • {category}"
            )

    else:
        print("[WARN] Not enough data to cluster.")
        # Still emit a global z-score summary CSV so you have it
        CL_OUT = os.path.join(CAT_OUT, "clusters")
        ensure_dir(CL_OUT)
        all_avg_edges = compute_avg_session_edges(pd.concat(team_dfs.values(), ignore_index=True))
        z_global = apply_zscore_filter(all_avg_edges.copy(), threshold=-9999.0)
        z_global_fp = os.path.join(CL_OUT, f"zscore_summary_{category}.csv")
        z_global[["from", "to", "count", "z_score"]].to_csv(z_global_fp, index=False)

print("\n[✅ DONE] All graphs written under:", OUTPUTS_ROOT)