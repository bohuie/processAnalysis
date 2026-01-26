import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env if it exists
load_dotenv(verbose=False)

from event_labelling.CodeStructure_Branching.main import process_all_teams as process_all_teams_cs
from event_labelling.PR.pr_label import process_all_teams as process_all_teams_pr
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing

# Continue with labeling steps
print("\nStep 2: Event Labelling & PR Analysis")
try:
    print("   • Processing Branching and Code Structure...")
    process_all_teams_cs()
    print("   [OK] Finished Branching Analysis\n")
except Exception as e:
    print(f"   [ERROR] Branching analysis error: {e}\n")

try:
    print("   • Processing PR Labels...")
    process_all_teams_pr()
    print("   [OK] Finished PR Analysis\n")
except Exception as e:
    print(f"   [ERROR] PR analysis error: {e}\n")

# Run process model analysis (BOTH datasets automatically)
print("\n📊 Step 3: Process Model Analysis (Both Datasets)")
print("   Processing for branching AND pr_labels automatically...\n")

try:
    print("   • Computing transition edges...")
    run_transition_edges()
    print("   ✓ Finished transition edges\n")
except Exception as e:
    print(f"   ⚠️  Transition edges error: {e}\n")

try:
    print("   • Computing z-scores...")
    run_zscore()
    print("   ✓ Finished z-scores\n")
except Exception as e:
    print(f"   ⚠️  Z-score error: {e}\n")

try:
    print("   • Computing clusters...")
    run_clustering()
    print("   ✓ Finished clustering\n")
except Exception as e:
    print(f"   ⚠️  Clustering error: {e}\n")

# Run process model analysis (BOTH datasets automatically)
print("\nStep 3: Process Model Analysis (Both Datasets)")
print("   Processing for branching AND pr_labels automatically...\n")

try:
    print("   • Computing transition edges...")
    run_transition_edges()
    print("   [OK] Finished transition edges\n")
except Exception as e:
    print(f"   [ERROR] Transition edges error: {e}\n")

try:
    print("   • Computing z-scores...")
    run_zscore()
    print("   [OK] Finished z-scores\n")
except Exception as e:
    print(f"   [ERROR] Z-score error: {e}\n")

try:
    print("   • Computing clusters...")
    run_clustering()
    print("   [OK] Finished clustering\n")
except Exception as e:
    print(f"   [ERROR] Clustering error: {e}\n")

try:
    print("   • Generating graphs...")
    run_graphing()
    print("   [OK] Finished graph generation\n")
except Exception as e:
    print(f"   [ERROR] Graph generation error: {e}\n")

print("=" * 70)
print("[COMPLETE] Pipeline Complete!")
print("=" * 70)
print("\nOutput locations:")
print("  • Branching analysis: data/outputs/branching/")
print("  • PR analysis: data/outputs/pr/")
print("  • Both datasets processed automatically - no environment variables needed!")