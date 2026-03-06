#!/usr/bin/env python3
# File: worker.py
# RunPod Serverless Worker for Chatterbox TTS
# Uses runpod.serverless.start() with handler from handler.py

import runpod.serverless
import handler
import concurrency

# Wrap the handler function for RunPod Serverless
runpod.serverless.start({
    "handler": handler.handler,
    "concurrency_modifier": concurrency.adjust_concurrency
})
