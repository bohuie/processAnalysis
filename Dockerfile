FROM python:3.11-slim

# System deps for graphviz and psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        graphviz \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

ENV PYTHONUNBUFFERED=1 \
    OUTPUT_ROOT=/app/data/outputs

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
