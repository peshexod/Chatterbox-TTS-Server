# Chatterbox TTS Server - RunPod Deployment

This directory contains files for deploying Chatterbox TTS on RunPod.

## Files

- **handler.py** - RunPod serverless handler function
- **runpod_server.py** - FastAPI server with health check and TTS endpoints
- **Dockerfile.runpod** - Docker image for RunPod
- **requirements-runpod.txt** - Python dependencies for RunPod

## Quick Start

### Option 1: Deploy using RunPod Console

1. Build and push the Docker image:
```bash
docker build -t chatterbox-tts-runpod -f Dockerfile.runpod .
docker tag chatterbox-tts-runpod your-registry/chatterbox-tts-runpod:latest
docker push your-registry/chatterbox-tts-runpod:latest
```

2. Deploy on RunPod:
   - Go to RunPod console
   - Create new pod with custom container
   - Use your image
   - Select GPU (recommended: RTX 4090 or A100)
   - Set port 8000

### Option 2: Deploy using runpod-cli

```bash
runpod pod create --image your-registry/chatterbox-tts-runpod --gpu-type RTX_4090 --cloud generic
```

## API Endpoints

When deployed, the server provides:

- `GET /health` - Health check
- `POST /tts` - Synthesize speech

### TTS Request Example

```json
{
  "text": "Hello, this is a test of the Chatterbox TTS system.",
  "language": "en",
  "temperature": 0.8,
  "exaggeration": 0.5,
  "cfg_weight": 0.5,
  "seed": 0
}
```

### With Voice Cloning

```json
{
  "text": "Hello, this is a test of the Chatterbox TTS system.",
  "reference_audio_url": "https://example.com/voice_sample.wav",
  "language": "en",
  "temperature": 0.8
}
```

### With S3 Upload

```json
{
  "text": "Hello, this is a test.",
  "storage": {
    "endpoint": "https://your-r2-endpoint.r2.cloudflarestorage.com",
    "bucket": "your-bucket",
    "access_key": "your-access-key",
    "secret_key": "your-secret-key",
    "region": "auto"
  },
  "temperature": 0.8
}
```

### Response

```json
{
  "status": "success",
  "audio": "<base64 encoded wav>",
  "format": "wav",
  "sample_rate": 24000
}
```

Or with S3 storage:

```json
{
  "status": "success",
  "audio_url": "https://your-r2-endpoint.r2.cloudflarestorage.com/bucket/filename.wav"
}
```

## Supported Languages

- English (en)
- Arabic (ar)
- Turkish (tr)
- German (de)
- French (fr)
- Dutch (nl)
- And more...

## Environment Variables

- `HF_HOME` - Hugging Face cache directory (default: /app/hf_cache)
- `TRANSFORMERS_CACHE` - Transformers cache directory
- `TORCH_CUDNN_V8_API_DISABLED` - Disable cuDNN v8 API for compatibility

## GPU Requirements

Recommended GPUs:
- RTX 4090 (24GB VRAM)
- A100 (40GB VRAM)
- A6000 (48GB VRAM)

Minimum: 16GB VRAM
