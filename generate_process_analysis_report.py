"""
Entry point for the combined PA+CA process analysis PDF report.

Usage:
    python generate_process_analysis_report.py \
        --pa-outputs /path/to/data/outputs \
        --pa-analysis /path/to/data/analysis \
        --ca-data     /path/to/data/json \
        --output-dir  /path/to/data/pdf/process_analysis
"""
import argparse
import sys
from pathlib import Path

from src.processors.process_analysis_report_generator import ProcessAnalysisReportGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Generate a combined process+collaboration analysis PDF."
    )
    parser.add_argument(
        "--pa-outputs",
        required=True,
        help="Path to PA data/outputs/ (contains branching/, pr/, communication/).",
    )
    parser.add_argument(
        "--pa-analysis",
        required=True,
        help="Path to PA data/analysis/ (table2_statistics.csv, team_level_data.csv, etc.).",
    )
    parser.add_argument(
        "--ca-data",
        required=True,
        help="Path to data/json/ directory (written by scripts/unified_github_data_pull.py or export_to_repos.py).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the generated PDF will be saved.",
    )
    parser.add_argument(
        "--file-name",
        default="process-analysis-report.pdf",
        help="Output PDF filename (default: process-analysis-report.pdf).",
    )
    args = parser.parse_args()

    outputs_path = Path(args.pa_outputs)
    analysis_path = Path(args.pa_analysis)
    ca_data_path = Path(args.ca_data)
    output_dir = Path(args.output_dir)

    if not outputs_path.exists():
        print(f"ERROR: PA outputs directory not found: {outputs_path}")
        sys.exit(1)

    if not analysis_path.exists():
        print(f"ERROR: PA analysis directory not found: {analysis_path}")
        sys.exit(1)

    if not ca_data_path.exists():
        print(f"WARNING: CA data directory not found: {ca_data_path} — CA section will be empty.")

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating combined process analysis report...")
    generator = ProcessAnalysisReportGenerator()
    generator.generate_report(
        pa_outputs_dir=outputs_path,
        pa_analysis_dir=analysis_path,
        ca_data_dir=ca_data_path,
        output_dir=output_dir,
        file_name=args.file_name,
    )
    print(f"Report saved to: {output_dir / args.file_name}")


if __name__ == "__main__":
    main()
