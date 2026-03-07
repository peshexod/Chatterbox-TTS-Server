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


def adjust_concurrency(current_concurrency):
    """
    RunPod concurrency modifier callback.
    Dynamically adjusts concurrency based on GPU/CPU load.
    
    Args:
        current_concurrency: Current number of running jobs
    
    Returns:
        int: New concurrency level to set
    """
    gpu_util = get_gpu_utilization()
    cpu_util = get_cpu_utilization()
    mem_util = get_memory_usage()
    
    # Limits
    max_concurrency = 10
    min_concurrency = 1
    
    # Thresholds
    gpu_high_threshold = 80
    cpu_high_threshold = 80
    mem_high_threshold = 80
    
    # Check if overloaded
    is_overloaded = (gpu_util >= gpu_high_threshold or 
                     cpu_util >= cpu_high_threshold or 
                     mem_util >= mem_high_threshold)
    
    if is_overloaded and current_concurrency > min_concurrency:
        # High load - reduce concurrency
        new_level = current_concurrency - 1
        print(f"[Concurrency] High load: GPU={gpu_util}%, CPU={cpu_util}%, MEM={mem_util}%. Reducing to {new_level}")
        return new_level
    
    elif current_concurrency < max_concurrency:
        # Low load - increase concurrency
        new_level = current_concurrency + 1
        print(f"[Concurrency] Low load: GPU={gpu_util}%, CPU={cpu_util}%, MEM={mem_util}%. Increasing to {new_level}")
        return new_level
    
    # Keep current concurrency
    return current_concurrency
