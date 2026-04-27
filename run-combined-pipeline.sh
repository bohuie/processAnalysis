#!/bin/bash
# Combined Pipeline Orchestration
# Runs PA and CA pipelines together with data sharing
# 1. Extract GitHub data (PA)
# 2. Generate process graphs (PA)
# 3. Share data with CA
# 4. Generate reports with combined data (CA)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PA_DIR="$SCRIPT_DIR"
CA_DIR="$(dirname "$SCRIPT_DIR")/collabAnalysis"

echo "=========================================="
echo "🚀 COMBINED PIPELINE ORCHESTRATION"
echo "=========================================="
echo "Root: $SCRIPT_DIR"
echo "PA: $PA_DIR"
echo "CA: $CA_DIR"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_step() {
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===================================================${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Step 1: Extract GitHub data for both repos
log_step "STEP 1: Extracting GitHub Data (PA)"
cd "$PA_DIR"
echo "Running: .venv/bin/python main.py"
.venv/bin/python main.py
log_success "PA data extraction and analysis complete"

# Step 2: Check that outputs were generated
log_step "STEP 2: Verifying PA Outputs"
if [ -d "$PA_DIR/data/outputs" ]; then
    log_success "PA outputs generated:"
    find "$PA_DIR/data/outputs" -type d -maxdepth 1 | xargs ls -ld
else
    echo "⚠ Warning: PA outputs directory not found"
fi

# Step 3: Prepare data for CA
log_step "STEP 3: Sharing Data with CA"

# Create CA data directory if it doesn't exist
mkdir -p "$CA_DIR/data"

# Copy/link PA outputs to CA
if [ -d "$PA_DIR/data/outputs" ]; then
    log_success "Copying PA process graphs to CA..."
    # Create a graphs directory in CA with PA outputs
    mkdir -p "$CA_DIR/data/graphs"
    cp -r "$PA_DIR/data/outputs"/* "$CA_DIR/data/graphs/" 2>/dev/null || log_warning "Some files may not have copied"
    log_success "Graphs copied to: $CA_DIR/data/graphs"
fi

# Optionally copy CSV data for report enhancement
if [ -d "$PA_DIR/data/csv" ]; then
    log_success "Copying extracted PR data to CA..."
    mkdir -p "$CA_DIR/data/pr_data"
    cp -r "$PA_DIR/data/csv"/* "$CA_DIR/data/pr_data/" 2>/dev/null || log_warning "Some CSV files may not have copied"
fi

# Step 4: Run CA report generation
log_step "STEP 4: Generating CA Reports (with PA Graphs)"
cd "$CA_DIR"

# Set PYTHONPATH for CA
export PYTHONPATH="$CA_DIR:$PYTHONPATH"

echo "Running: .venv/bin/python example/app.py"
.venv/bin/python example/app.py

log_success "CA report generation complete"

# Step 5: Verify outputs
log_step "STEP 5: Verifying Final Outputs"

echo ""
echo "📊 Process Analysis (PA) Outputs:"
if [ -d "$PA_DIR/data/outputs" ]; then
    find "$PA_DIR/data/outputs" -name "*.svg" -o -name "*.png" | head -10
    echo "   See: $PA_DIR/data/outputs/"
else
    log_warning "PA outputs not found"
fi

echo ""
echo "📄 Collaboration Analysis (CA) Outputs:"
if [ -d "$CA_DIR/data/reports" ]; then
    find "$CA_DIR/data/reports" -type f | head -10
    echo "   See: $CA_DIR/data/reports/"
elif [ -d "$CA_DIR/data" ]; then
    ls -la "$CA_DIR/data/" | grep -v "^d" | head -10
    echo "   See: $CA_DIR/data/"
else
    log_warning "CA report outputs not found"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ COMBINED PIPELINE COMPLETE!${NC}"
echo "=========================================="
echo ""
echo "Summary:"
echo "1. ✓ Extracted GitHub data for all repositories"
echo "2. ✓ Generated PA process graphs and statistics"
echo "3. ✓ Shared process graphs with CA"
echo "4. ✓ Generated CA reports with combined data"
echo ""
echo "Next steps:"
echo "- Review PA graphs in: $PA_DIR/data/outputs/"
echo "- Review CA reports in: $CA_DIR/data/"
echo ""
