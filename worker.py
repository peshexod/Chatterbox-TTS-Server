#!/usr/bin/env python3
# File: worker.py
# RunPod Serverless Worker for Chatterbox TTS
# Uses runpod.serverless.start() with handler and concurrency_modifier

import runpod.serverless
import handler

# Simple concurrency modifier - RunPod handles it automatically
def concurrency_modifier(job_count, active_jobs):
    # Let RunPod handle concurrency automatically
    return None

# Start RunPod Serverless with handler
runpod.serverless.start({
    "handler": handler.handler,
    "concurrency_modifier": concurrency_modifier
})
