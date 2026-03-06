# ============================================================================
# Dockerfile for RunPod Serverless - Chatterbox TTS
# ============================================================================
# This Dockerfile is designed for RunPod Serverless Endpoints
# It does NOT run a server - instead it packages the handler function
# that RunPod will call directly

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/app/hf_cache
ENV TRANSFORMERS_CACHE=/app/hf_cache

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements-runpod.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-runpod.txt

# Copy application code
COPY engine.py .
COPY handler.py .
COPY worker.py .
COPY concurrency.py .
COPY models.py .
COPY config.py .
COPY utils.py .
COPY download_model.py .

# Create required directories
RUN mkdir -p model_cache reference_audio outputs voices logs hf_cache

# For serverless, use runpod.serverless.start() via worker.py
# RunPod will call handler() function through the worker
CMD ["python", "worker.py"]

