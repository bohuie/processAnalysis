#!/bin/bash
# Setup and run the process analysis pipeline in Docker

set -e

echo "=========================================="
echo "Process Analysis Pipeline - Docker Setup"
echo "=========================================="

# Step 1: Build the Docker image
echo ""
echo "Step 1: Building Docker image..."
docker-compose -f docker-compose.process.yml build

# Step 2: Start Ollama service
echo ""
echo "Step 2: Starting Ollama service..."
docker-compose -f docker-compose.process.yml up -d llm

# Wait for Ollama to be healthy
echo ""
echo "Waiting for Ollama to be ready..."
sleep 10

# Step 3: Pull the required model
echo ""
echo "Step 3: Pulling llama3.2:3b model (this may take a few minutes)..."
docker-compose -f docker-compose.process.yml exec llm ollama pull llama3.2:3b

# Step 4: Verify model is available
echo ""
echo "Step 4: Verifying model availability..."
docker-compose -f docker-compose.process.yml exec llm ollama list

# Step 5: Run the analysis pipeline
echo ""
echo "=========================================="
echo "Starting Process Analysis Pipeline"
echo "=========================================="
docker-compose -f docker-compose.process.yml up process

echo ""
echo "=========================================="
echo "Pipeline Complete!"
echo "=========================================="
echo "Results are available in ./data/outputs/ and ./data/analysis/"
