#!/usr/bin/env python3
"""
Adaptive Concurrency Modifier for RunPod Serverless
Monitors GPU/CPU usage and adjusts concurrency dynamically
"""

import os

# Try to import monitoring libraries
try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Configuration
GPU_THRESHOLD_HIGH = 90  # At 90% GPU - stop accepting new jobs
GPU_THRESHOLD_LOW = 50  # At 50% GPU - resume accepting jobs
CPU_THRESHOLD_HIGH = 90  # At 90% CPU - stop accepting new jobs

# Initialize NVML
if NVML_AVAILABLE:
    try:
        pynvml.nvmlInit()
        GPU_COUNT = pynvml.nvmlDeviceGetCount()
    except Exception as e:
        print(f"Warning: NVML init failed: {e}")
        GPU_COUNT = 0
else:
    GPU_COUNT = 0


def get_gpu_utilization():
    """Get current GPU utilization percentage"""
    if not NVML_AVAILABLE or GPU_COUNT == 0:
        return 0
    
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        return utilization.gpu
    except Exception:
        return 0


def get_cpu_utilization():
    """Get current CPU utilization percentage"""
    if not PSUTIL_AVAILABLE:
        return 0
    
    try:
        return psutil.cpu_percent(interval=0.1)
    except Exception:
        return 0


def get_memory_usage():
    """Get current memory usage percentage"""
    if not PSUTIL_AVAILABLE:
        return 0
    
    try:
        return psutil.virtual_memory().percent
    except Exception:
        return 0


def adjust_concurrency(job_count, active_jobs):
    """
    RunPod concurrency modifier callback.
    Called before each job is dispatched.
    
    Args:
        job_count: Total number of jobs in the system
        active_jobs: Number of currently running jobs
    
    Returns:
        int or None: Maximum number of concurrent jobs to allow, or None for default
    """
    gpu_util = get_gpu_utilization()
    cpu_util = get_cpu_utilization()
    mem_util = get_memory_usage()
    
    # If any resource is overloaded, reduce concurrency
    if gpu_util >= GPU_THRESHOLD_HIGH or cpu_util >= CPU_THRESHOLD_HIGH or mem_util >= 90:
        # Reduce concurrency - allow fewer jobs
        new_limit = max(1, active_jobs - 1)
        print(f"[Concurrency] High load: GPU={gpu_util}%, CPU={cpu_util}%, MEM={mem_util}%. Limiting to {new_limit} concurrent jobs")
        return new_limit
    
    # If resources are available, allow more jobs
    if gpu_util < GPU_THRESHOLD_LOW and cpu_util < 70 and mem_util < 70:
        # Allow up to 2 concurrent jobs if resources available
        if active_jobs < 2:
            print(f"[Concurrency] Low load: GPU={gpu_util}%, CPU={cpu_util}%, MEM={mem_util}%. Allowing more jobs")
            return None  # Let RunPod decide
    
    return None  # Keep current concurrency
