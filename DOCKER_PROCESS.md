# Running Process Analysis Pipeline with Docker

This guide explains how to run the process analysis pipeline (`process_model_only.py`) in Docker with Ollama.

## Quick Start

### Option 1: Use the automated script (recommended)

```bash
./run-docker-process.sh
```

This script will:
1. Build the Docker image
2. Start Ollama service
3. Pull the llama3.2:3b model
4. Run the analysis pipeline

### Option 2: Manual setup

#### 1. Build and start services

```bash
docker-compose -f docker-compose.process.yml up -d llm
```

#### 2. Wait for Ollama to be ready (about 10-30 seconds)

```bash
docker-compose -f docker-compose.process.yml ps
```

#### 3. Pull the required model

```bash
docker-compose -f docker-compose.process.yml exec llm ollama pull llama3.2:3b
```

#### 4. Verify model is available

```bash
docker-compose -f docker-compose.process.yml exec llm ollama list
```

#### 5. Run the analysis pipeline

```bash
docker-compose -f docker-compose.process.yml up process
```

## Configuration

### Environment Variables

The pipeline uses the following environment variables (set in `docker-compose.process.yml`):

- `AI_MODE=offline` - Uses local Ollama instead of Groq API
- `OLLAMA_HOST=http://llm:11434` - Ollama service hostname in Docker network
- `PYTHONUNBUFFERED=1` - Show Python output in real-time

### Required Files

Make sure you have the following before running:
- Input data in `./data/csv/` or `./data/graph_labels/clean/`
- `.env` file with any additional configuration (optional)

## Outputs

Results will be written to:
- `./data/outputs/branching/` - Branching analysis results
- `./data/outputs/pr/` - PR analysis results  
- `./data/analysis/` - Team-level statistics

## Troubleshooting

### Ollama connection errors

If you see connection errors:

```bash
# Check Ollama is running
docker-compose -f docker-compose.process.yml ps llm

# Check Ollama logs
docker-compose -f docker-compose.process.yml logs llm

# Restart Ollama
docker-compose -f docker-compose.process.yml restart llm
```

### Model not found errors

```bash
# List available models
docker-compose -f docker-compose.process.yml exec llm ollama list

# Pull the required model
docker-compose -f docker-compose.process.yml exec llm ollama pull llama3.2:3b
```

### View pipeline logs

```bash
docker-compose -f docker-compose.process.yml logs -f process
```

## Cleanup

Stop all services:

```bash
docker-compose -f docker-compose.process.yml down
```

Remove all data (including Ollama models):

```bash
docker-compose -f docker-compose.process.yml down -v
```

## Advanced: Using Different Models

To use a different Ollama model, pull it first and update your code:

```bash
# Pull a different model
docker-compose -f docker-compose.process.yml exec llm ollama pull llama2

# Update DEFAULT_MODEL_NAME in src/utils/ollama_offline.py
```
