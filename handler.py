# File: handler.py
# RunPod handler for Chatterbox TTS Server
# Handles HTTP requests for text-to-speech generation with optional voice cloning

import os
import io
import logging
import base64
import tempfile
import uuid
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import torch
import numpy as np
import soundfile as sf

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Import engine from local module
import engine


# --- Global State ---
_model_loaded = False


def _load_model() -> bool:
    """
    Load the TTS model if not already loaded.
    Returns True if model is loaded successfully.
    """
    global _model_loaded
    
    if _model_loaded:
        logger.info("Model already loaded")
        return True
    
    logger.info("Loading Chatterbox TTS model...")
    success = engine.load_model()
    if success:
        _model_loaded = True
        logger.info("Model loaded successfully")
    else:
        logger.error("Failed to load model")
    
    return success


def _download_file(url: str, temp_dir: Path) -> Optional[Path]:
    """
    Download a file from URL to a temporary directory.
    
    Args:
        url: URL to download from
        temp_dir: Directory to save the file
        
    Returns:
        Path to downloaded file or None if failed
    """
    import requests
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Determine filename from URL or content-disposition
        filename = None
        if 'content-disposition' in response.headers:
            import re
            match = re.search(r'filename="?([^";\n]+)"?', response.headers['content-disposition'])
            if match:
                filename = match.group(1)
        
        if not filename:
            # Extract from URL
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


def _upload_to_s3(audio_bytes: bytes, storage: Dict[str, str]) -> Optional[str]:
    """
    Upload audio bytes to S3-compatible storage.
    
    Args:
        audio_bytes: Raw audio data
        storage: S3 credentials dict with keys:
            - endpoint: S3 endpoint URL
            - bucket: Bucket name
            - access_key: S3 access key
            - secret_key: S3 secret key
            - region: S3 region (optional)
            
    Returns:
        Public URL of uploaded file or None if failed
    """
    import boto3
    from botocore.config import Config
    
    try:
        # Generate unique filename
        filename = f"tts_output_{uuid.uuid4().hex[:8]}.wav"
        
        # Create S3 client
        s3_params = {
            'endpoint_url': storage.get('endpoint'),
            'aws_access_key_id': storage.get('access_key'),
            'aws_secret_access_key': storage.get('secret_key'),
        }
        
        if storage.get('region'):
            s3_params['region_name'] = storage.get('region')
        
        # Use path-style addressing for compatibility
        s3_params['config'] = Config(s33={'addressing_style': 'path'})
        
        s3_client = boto3.client('s3', **s3_params)
        
        # Upload
        bucket = storage.get('bucket')
        s3_client.put_object(
            Bucket=bucket,
            Key=filename,
            Body=audio_bytes,
            ContentType='audio/wav'
        )
        
        # Generate public URL
        # For most S3-compatible storages (including Cloudflare R2)
        endpoint = storage.get('endpoint', '').rstrip('/')
        if 'amazonaws.com' in endpoint or 'cloudflare' in endpoint:
            # Use virtual-hosted style for AWS/Cloudflare
            public_url = f"{endpoint}/{bucket}/{filename}"
        else:
            # Path style for other S3-compatible
            public_url = f"{endpoint}/{bucket}/{filename}"
        
        logger.info(f"Uploaded to S3: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Failed to upload to S3: {e}")
        return None


def _synthesize_audio(
    text: str,
    reference_audio_path: Optional[str] = None,
    temperature: float = 0.8,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    seed: int = 0,
    language: str = "en"
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Synthesize audio from text using the TTS engine.
    
    Args:
        text: Text to synthesize
        reference_audio_path: Path to reference audio for voice cloning
        temperature: Sampling temperature
        exaggeration: Expressiveness
        cfg_weight: CFG weight
        seed: Random seed
        language: Language code
        
    Returns:
        Tuple of (audio_bytes, error_message)
    """
    try:
        # Synthesize
        wav_tensor, sample_rate = engine.synthesize(
            text=text,
            audio_prompt_path=reference_audio_path,
            temperature=temperature,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            seed=seed,
            language=language
        )
        
        if wav_tensor is None:
            return None, "Synthesis failed - model returned None"
        
        # Convert to numpy and then to WAV bytes
        audio_np = wav_tensor.cpu().numpy()
        
        # Handle different output shapes
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()
        
        # Normalize to [-1, 1] if needed
        max_val = np.abs(audio_np).max()
        if max_val > 1.0:
            audio_np = audio_np / max_val
        
        # Create WAV in memory
        buffer = io.BytesIO()
        sf.write(buffer, audio_np, sample_rate, format='WAV')
        buffer.seek(0)
        audio_bytes = buffer.read()
        
        return audio_bytes, None
        
    except Exception as e:
        logger.error(f"Synthesis error: {e}")
        return None, str(e)


def _convert_wav_to_mp3(wav_bytes: bytes, bitrate: str = "192k") -> Optional[bytes]:
    """
    Convert WAV audio to MP3 using ffmpeg.
    
    Args:
        wav_bytes: Raw WAV audio data
        bitrate: MP3 bitrate (default: 192k)
        
    Returns:
        MP3 audio bytes or None if failed
    """
    try:
        process = subprocess.Popen(
            ['ffmpeg', '-i', '-', '-b:a', bitrate, '-f', 'mp3', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        mp3_bytes, stderr = process.communicate(input=wav_bytes, timeout=60)
        
        if process.returncode != 0:
            logger.error(f"ffmpeg error: {stderr.decode()}")
            return None
        
        return mp3_bytes
        
    except Exception as e:
        logger.error(f"Failed to convert to MP3: {e}")
        return None


def handler(event, context):
    """
    Main RunPod handler function.
    
    Args:
        event: Dict containing request parameters
            - text: str - Text to synthesize (required)
            - reference_audio_url: str - URL of reference audio for voice cloning (optional)
            - storage: dict - S3 credentials for upload (optional)
                - endpoint: str
                - bucket: str
                - access_key: str
                - secret_key: str
                - region: str (optional)
            - temperature: float - Sampling temperature (default: 0.8)
            - exaggeration: float - Expressiveness (default: 0.5)
            - cfg_weight: float - CFG weight (default: 0.5)
            - seed: int - Random seed (default: 0)
            - language: str - Language code (default: "en")
            
        context: RunPod context (unused)
    
    Returns:
        Dict with response:
            - If storage provided: {"status": "success", "audio_url": "..."}
            - If no storage: {"status": "success", "audio": "<base64 encoded wav>"}
            - On error: {"status": "error", "error": "..."}
    """
    global _model_loaded
    
    # Load model if not loaded
    if not _model_loaded:
        if not _load_model():
            return {
                "status": "error",
                "error": "Failed to load TTS model"
            }
    
    # Extract parameters from event
    text = event.get("text", "")
    reference_audio_url = event.get("reference_audio_url")
    storage = event.get("storage")
    
    # Generation parameters
    temperature = event.get("temperature", 0.8)
    exaggeration = event.get("exaggeration", 0.5)
    cfg_weight = event.get("cfg_weight", 0.5)
    seed = event.get("seed", 0)
    language = event.get("language", "en")
    output_format = event.get("format", "wav")  # "wav" or "mp3"
    
    # Validate required params
    if not text:
        return {
            "status": "error",
            "error": "Missing required parameter: text"
        }
    
    logger.info(f"Processing TTS request: text={text[:50]}..., lang={language}")
    
    # Create temp directory for reference audio
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        reference_audio_path = None
        
        # Download reference audio if provided
        if reference_audio_url:
            logger.info(f"Downloading reference audio from {reference_audio_url}")
            reference_audio_path = _download_file(reference_audio_url, temp_path)
            if not reference_audio_path:
                return {
                    "status": "error",
                    "error": f"Failed to download reference audio from {reference_audio_url}"
                }
        
        # Synthesize audio
        audio_bytes, error = _synthesize_audio(
            text=text,
            reference_audio_path=str(reference_audio_path) if reference_audio_path else None,
            temperature=temperature,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            seed=seed,
            language=language
        )
        
        if error:
            return {
                "status": "error",
                "error": error
            }
        
        # Handle output based on storage
        if storage:
            # Upload to S3
            audio_url = _upload_to_s3(audio_bytes, storage)
            if not audio_url:
                return {
                    "status": "error",
                    "error": "Failed to upload audio to S3"
                }
            
            return {
                "status": "success",
                "audio_url": audio_url
            }
        else:
            # Return base64 encoded audio
            # Convert to MP3 if requested
            if output_format.lower() == "mp3":
                mp3_bytes = _convert_wav_to_mp3(audio_bytes)
                if mp3_bytes:
                    audio_bytes = mp3_bytes
                    content_type = "audio/mpeg"
                else:
                    logger.warning("MP3 conversion failed, returning WAV")
                    output_format = "wav"
                    content_type = "audio/wav"
            else:
                content_type = "audio/wav"
            
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            return {
                "status": "success",
                "audio": audio_b64,
                "format": output_format.lower(),
                "content_type": content_type
            }


# For local testing
if __name__ == "__main__":
    # Test the handler
    test_event = {
        "text": "Hello, this is a test of the Chatterbox TTS system.",
        "language": "en",
        "temperature": 0.8
    }
    
    result = handler(test_event, None)
    print(f"Result: {result}")
