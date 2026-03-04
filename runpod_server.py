# File: runpod_server.py
# Simple FastAPI server for RunPod with health check endpoint
# This serves as an alternative entry point that provides HTTP endpoints

import os
import io
import logging
import base64
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import torch
import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import engine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatterbox TTS RunPod")


class TTSRequest(BaseModel):
    text: str
    reference_audio_url: Optional[str] = None
    temperature: float = 0.8
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    seed: int = 0
    language: str = "en"


class StorageConfig(BaseModel):
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: Optional[str] = None


class TTSRequestWithStorage(BaseModel):
    text: str
    reference_audio_url: Optional[str] = None
    storage: Optional[StorageConfig] = None
    temperature: float = 0.8
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    seed: int = 0
    language: str = "en"


_model_loaded = False


@app.on_event("startup")
async def startup():
    global _model_loaded
    logger.info("Loading Chatterbox TTS model...")
    success = engine.load_model()
    if success:
        _model_loaded = True
        logger.info("Model loaded successfully")
    else:
        logger.error("Failed to load model")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy" if _model_loaded else "loading",
        "model_loaded": _model_loaded
    }


def _download_file(url: str, temp_dir: Path) -> Optional[Path]:
    import requests
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        import re
        filename = None
        if 'content-disposition' in response.headers:
            match = re.search(r'filename="?([^";\n]+)"?', response.headers['content-disposition'])
            if match:
                filename = match.group(1)
        
        if not filename:
            filename = url.split('/')[-1].split('?')[0]
            if not filename or '.' not in filename:
                filename = f"audio_{uuid.uuid4().hex[:8]}.wav"
        
        filepath = temp_dir / filename
        filepath.write_bytes(response.content)
        logger.info(f"Downloaded {url} to {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def _upload_to_s3(audio_bytes: bytes, storage: dict) -> Optional[str]:
    import boto3
    from botocore.config import Config
    
    try:
        filename = f"tts_output_{uuid.uuid4().hex[:8]}.wav"
        
        s3_params = {
            'endpoint_url': storage.get('endpoint'),
            'aws_access_key_id': storage.get('access_key'),
            'aws_secret_access_key': storage.get('secret_key'),
        }
        
        if storage.get('region'):
            s3_params['region_name'] = storage.get('region')
        
        s3_params['config'] = Config(s3={'addressing_style': 'path'})
        
        s3_client = boto3.client('s3', **s3_params)
        
        bucket = storage.get('bucket')
        s3_client.put_object(
            Bucket=bucket,
            Key=filename,
            Body=audio_bytes,
            ContentType='audio/wav'
        )
        
        endpoint = storage.get('endpoint', '').rstrip('/')
        public_url = f"{endpoint}/{bucket}/{filename}"
        
        logger.info(f"Uploaded to S3: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        return None


@app.post("/tts")
async def synthesize(request: TTSRequestWithStorage):
    if not _model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    if not request.text:
        raise HTTPException(status_code=400, detail="Missing text parameter")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        reference_audio_path = None
        
        if request.reference_audio_url:
            reference_audio_path = _download_file(request.reference_audio_url, temp_path)
            if not reference_audio_path:
                raise HTTPException(status_code=400, detail="Failed to download reference audio")
        
        try:
            wav_tensor, sample_rate = engine.synthesize(
                text=request.text,
                audio_prompt_path=str(reference_audio_path) if reference_audio_path else None,
                temperature=request.temperature,
                exaggeration=request.exaggeration,
                cfg_weight=request.cfg_weight,
                seed=request.seed,
                language=request.language
            )
            
            if wav_tensor is None:
                raise HTTPException(status_code=500, detail="Synthesis failed")
            
            audio_np = wav_tensor.cpu().numpy()
            if audio_np.ndim > 1:
                audio_np = audio_np.squeeze()
            
            max_val = np.abs(audio_np).max()
            if max_val > 1.0:
                audio_np = audio_np / max_val
            
            buffer = io.BytesIO()
            sf.write(buffer, audio_np, sample_rate, format='WAV')
            buffer.seek(0)
            audio_bytes = buffer.read()
            
            if request.storage:
                audio_url = _upload_to_s3(audio_bytes, request.storage.dict())
                if not audio_url:
                    raise HTTPException(status_code=500, detail="Failed to upload to S3")
                return JSONResponse({"status": "success", "audio_url": audio_url})
            else:
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                return JSONResponse({
                    "status": "success",
                    "audio": audio_b64,
                    "format": "wav",
                    "sample_rate": sample_rate
                })
                
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
