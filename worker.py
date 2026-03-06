#!/usr/bin/env python3
# File: worker.py
# RunPod Serverless Worker for Chatterbox TTS
# Uses runpod.serverless.start() with handler and concurrency_modifier

import runpod.serverless
import handler
import concurrency

# Start RunPod Serverless with handler and adaptive concurrency
runpod.serverless.start({
    "handler": handler.handler,
    "concurrency_modifier": concurrency.adjust_concurrency
})
