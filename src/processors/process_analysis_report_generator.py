"""
Generates a combined PDF report from processAnalysis (PA) + collabAnalysis (CA) outputs.

Data sources:
  PA graphs   — Markov process model PNGs (branching, PR, communication datasets)
  PA metrics  — table2_statistics.csv, team_level_data.csv, extreme_teams.csv
  CA data     — PR and review-comment CSVs extracted by ca_batch_extract.py

Called by generate_process_analysis_report.py (Docker entrypoint invoked by
processAnalysis/run-combined-report.sh). Not a replacement for ReportGeneratorPipeline.
"""
import base64
import glob
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import jinja2
import pandas as pd
import pdfkit

from src.utils.path_to_wkhtmltopdf import get_path_to_wkhtmltopdf


_TEMPLATE_PATH = "src/templates/process-analysis-report-template.html"
_DATASETS = ["branching", "pr", "communication"]


def _png_to_b64(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _load_csv(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as exc:
        print(f"[WARN] Could not load {path}: {exc}")
        return None


class ProcessAnalysisReportGenerator:
    def __init__(self) -> None:
        wkhtmltopdf_path = get_path_to_wkhtmltopdf() or "/usr/bin/wkhtmltopdf"
        self.pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

    # ------------------------------------------------------------------
    # PA: graph collection
    # ------------------------------------------------------------------

    def _collect_dataset(self, outputs_dir: Path, dataset: str) -> dict:
        """Return team and cluster graph data (base64 PNGs) for one dataset."""
        dataset_dir = outputs_dir / dataset
        teams: list[dict] = []
        clusters: list[dict] = []

        if not dataset_dir.exists():
            return {"name": dataset, "teams": teams, "clusters": clusters}

        for team_dir in sorted(dataset_dir.glob("year-long-project-team-*")):
            team_num = team_dir.name.replace("year-long-project-team-", "")
            overall_b64 = _png_to_b64(
                team_dir / "team_overall" / f"team{team_num}_overall.png"
            )
            avg_b64 = _png_to_b64(
                team_dir / "team_avg_session" / f"team{team_num}_avg_session.png"
            )
            if overall_b64 or avg_b64:
                teams.append(
                    {
                        "name": team_dir.name,
                        "team_num": team_num,
                        "overall_b64": overall_b64,
                        "avg_b64": avg_b64,
                    }
                )

        clusters_dir = dataset_dir / "clusters"
        if clusters_dir.exists():
            for cluster_dir in sorted(clusters_dir.glob("cluster*")):
                b64 = _png_to_b64(cluster_dir / "cluster_avg_session.png")
                if b64:
                    clusters.append({"name": cluster_dir.name, "b64": b64})

        return {"name": dataset, "teams": teams, "clusters": clusters}

    # ------------------------------------------------------------------
    # CA: collaboration metrics from exported JSON files
    # (written by scripts/export_to_repos.py from the unified data pull)
    # ------------------------------------------------------------------

    def _load_ca_repo_stats(self, ca_data_dir: Path) -> list[dict]:
        """
        Scan ca_data_dir/json/ for per-repo directories produced by export_to_repos.py.
        Each repo directory contains:
          {repo}_all_pull_requests.json  — list of PR objects  → PR count
          {repo}_commits_by_day.json     — {date: {author: n}} → total commit count

        Returns one dict per repo found.
        """
        if not ca_data_dir.exists():
            return []

        json_root = ca_data_dir
        repo_stats: list[dict] = []

        for repo_dir in sorted(json_root.iterdir()):
            if not repo_dir.is_dir():
                continue
            repo_name = repo_dir.name

            # PR count from all_pull_requests.json
            pr_json = repo_dir / f"{repo_name}_all_pull_requests.json"
            pr_count = 0
            if pr_json.exists():
                try:
                    import json as _json
                    with open(pr_json) as f:
                        data = _json.load(f)
                    pr_count = len(data) if isinstance(data, list) else 0
                except Exception:
                    pass

            # Commit count from commits_by_day.json
            cbd_json = repo_dir / f"{repo_name}_commits_by_day.json"
            commit_count = 0
            if cbd_json.exists():
                try:
                    import json as _json
                    with open(cbd_json) as f:
                        data = _json.load(f)
                    commit_count = sum(
                        sum(v.values()) if isinstance(v, dict) else 0
                        for v in data.values()
                    )
                except Exception:
                    pass

            if pr_count > 0 or commit_count > 0:
                repo_stats.append({
                    "repo": repo_name,
                    "pr_count": pr_count,
                    "commit_count": commit_count,
                })

        return repo_stats

    # ------------------------------------------------------------------
    # Build per-team deep-dive (metrics + CA stats + all graphs)
    # ------------------------------------------------------------------

    def _build_team_deep_dives(
        self,
        team_stats: list[dict],
        ca_repo_stats: list[dict],
        datasets: list[dict],
        extreme_df,
    ) -> list[dict]:
        ca_by_repo = {r["repo"]: r for r in ca_repo_stats}

        # Index graphs by (dataset_name, team_name)
        graphs_by_team: dict[str, dict] = {}
        for ds in datasets:
            for t in ds["teams"]:
                graphs_by_team.setdefault(t["name"], {})[ds["name"]] = {
                    "overall_b64": t["overall_b64"],
                    "avg_b64": t["avg_b64"],
                }

        extreme_teams: set[str] = set()
        extreme_label: dict[str, str] = {}
        if extreme_df is not None and not extreme_df.empty:
            for _, row in extreme_df.iterrows():
                extreme_teams.add(row["Team"])
                extreme_label[row["Team"]] = row["Type"]

        dives = []
        for ts in sorted(team_stats, key=lambda r: r["Team"]):
            name = ts["Team"]
            display = (
                name.replace("year-long-project-", "")
                    .replace("-", " ")
                    .title()
            )
            dives.append({
                "name": name,
                "display_name": display,
                "metrics": ts,
                "ca": ca_by_repo.get(name, {}),
                "graphs": graphs_by_team.get(name, {}),
                "extreme_label": extreme_label.get(name),
            })
        return dives

    # ------------------------------------------------------------------
    # Build template context
    # ------------------------------------------------------------------

    def _build_context(
        self,
        pa_outputs_dir: Path,
        pa_analysis_dir: Path,
        ca_data_dir: Path,
    ) -> dict:
        # PA metrics
        table2_df = _load_csv(pa_analysis_dir / "table2_statistics.csv")
        team_df = _load_csv(pa_analysis_dir / "team_level_data.csv")
        extreme_df = _load_csv(pa_analysis_dir / "extreme_teams.csv")

        table2_rows = table2_df.to_dict("records") if table2_df is not None else []
        team_stats = team_df.to_dict("records") if team_df is not None else []

        most_productive: Optional[dict] = None
        least_productive: Optional[dict] = None
        if extreme_df is not None and not extreme_df.empty:
            mp = extreme_df[extreme_df["Type"] == "Most Productive"]
            lp = extreme_df[extreme_df["Type"] == "Least Productive"]
            if not mp.empty:
                most_productive = mp.iloc[0].to_dict()
            if not lp.empty:
                least_productive = lp.iloc[0].to_dict()

        # PA graphs
        datasets = [
            self._collect_dataset(pa_outputs_dir, ds) for ds in _DATASETS
        ]
        total_graphs = sum(
            len(ds["teams"]) + len(ds["clusters"]) for ds in datasets
        )

        # CA collaboration metrics
        ca_repo_stats = self._load_ca_repo_stats(ca_data_dir)

        # Per-team deep dives (metrics + CA + graphs combined)
        team_deep_dives = self._build_team_deep_dives(
            team_stats, ca_repo_stats, datasets, extreme_df
        )

        # Cluster-only view (for dedicated cluster section)
        cluster_sections = [
            {"name": ds["name"], "clusters": ds["clusters"]}
            for ds in datasets
            if ds["clusters"]
        ]

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "table2_rows": table2_rows,
            "team_stats": team_stats,
            "most_productive": most_productive,
            "least_productive": least_productive,
            "datasets": datasets,
            "total_graphs": total_graphs,
            "ca_repo_stats": ca_repo_stats,
            "team_deep_dives": team_deep_dives,
            "cluster_sections": cluster_sections,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_report(
        self,
        pa_outputs_dir: Path,
        pa_analysis_dir: Path,
        ca_data_dir: Path,
        output_dir: Path,
        file_name: str = "process-analysis-report.pdf",
    ) -> None:
        """Generate the combined PDF report.

        Args:
            pa_outputs_dir: PA data/outputs/ (branching/, pr/, communication/ sub-dirs)
            pa_analysis_dir: PA data/analysis/ (industrial metrics CSVs)
            ca_data_dir: CA data/json/ (per-repo JSON from unified_github_data_pull.py)
            output_dir: Directory where the PDF is written.
            file_name: Output filename.
        """
        print("  Loading metrics, CA data, and graph images...")
        context = self._build_context(pa_outputs_dir, pa_analysis_dir, ca_data_dir)

        print(
            f"  PA teams: {len(context['team_stats'])}, "
            f"graphs: {context['total_graphs']}, "
            f"CA repos: {len(context['ca_repo_stats'])}"
        )

        print("  Rendering HTML template...")
        loader = jinja2.FileSystemLoader(["./", "../../"])
        env = jinja2.Environment(loader=loader)
        template = env.get_template(_TEMPLATE_PATH)
        html = template.render(context)

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = str(output_dir / file_name)

        print(f"  Writing PDF → {dest}")
        pdfkit.from_string(
            html,
            dest,
            configuration=self.pdfkit_config,
            options={"enable-local-file-access": ""},
        )
