# File: concurrency.py
# Adaptive concurrency modifier for RunPod Serverless
# Dynamically adjusts worker concurrency based on GPU/CPU/RAM metrics

import os
import logging
import threading

logger = logging.getLogger(__name__)

# Configuration for A6000 (48GB)
MAX_CONCURRENCY = 15
MIN_CONCURRENCY = 1

# Thresholds
GPU_MEM_THRESHOLD_HIGH = 85  # % - reduce if above
GPU_MEM_THRESHOLD_LOW = 60    # % - can scale up if below
CPU_THRESHOLD_HIGH = 80       # % - reduce if above
CPU_THRESHOLD_LOW = 50        # % - can scale up if below

# Try to import pynvml for GPU monitoring
_pynvml_available = False
_nvml_handle = None

try:
    import pynvml
    pynvml.nvmlInit()
    _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    _pynvml_available = True
    logger.info("NVML initialized for GPU monitoring")
except Exception as e:
    logger.warning(f"NVML not available: {e}")

# Try to import psutil for CPU/RAM monitoring
_psutil_available = False
try:
    import psutil
    _psutil_available = True
    logger.info("psutil available for CPU/RAM monitoring")
except Exception as e:
    logger.warning(f"psutil not available: {e}")


def get_system_metrics() -> dict:
    """
    Get current system metrics (GPU, CPU, RAM).
    
    Returns:
        dict with keys:
            - gpu_mem_pct: GPU memory usage percentage
            - gpu_util_pct: GPU utilization percentage  
            - cpu_pct: CPU usage percentage
            - ram_pct: RAM usage percentage
    """
    metrics = {
        "gpu_mem_pct": 0,
        "gpu_util_pct": 0,
        "cpu_pct": 0,
        "ram_pct": 0
    }
    
    # GPU metrics
    if _pynvml_available and _nvml_handle is not None:
        try:
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
            metrics["gpu_mem_pct"] = (mem_info.used / mem_info.total) * 100
            
            util = pynvml.nvmlDeviceGetUtilizationRates(_nvml_handle)
            metrics["gpu_util_pct"] = util.gpu
        except Exception as e:
            logger.warning(f"Failed to get GPU metrics: {e}")
    
    # CPU/RAM metrics
    if _psutil_available:
        try:
            metrics["cpu_pct"] = psutil.cpu_percent(interval=0.1)
            metrics["ram_pct"] = psutil.virtual_memory().percent
        except Exception as e:
            logger.warning(f"Failed to get CPU/RAM metrics: {e}")
    
    return metrics


def adjust_concurrency(current_concurrency: int) -> int:
    """
    Adjust worker concurrency based on system resource usage.
    
    Called periodically by RunPod during worker lifecycle.
    
    Args:
        current_concurrency: Current concurrency level
        
    Returns:
        New concurrency level to use
    """
    metrics = get_system_metrics()
    
    logger.info(
        f"Concurrency check: current={current_concurrency}, "
        f"gpu_mem={metrics['gpu_mem_pct']:.1f}%, "
        f"gpu_util={metrics['gpu_util_pct']:.1f}%, "
        f"cpu={metrics['cpu_pct']:.1f}%, "
        f"ram={metrics['ram_pct']:.1f}%"
    )
    
    # Check if we should scale DOWN (high load)
    if (metrics["gpu_mem_pct"] > GPU_MEM_THRESHOLD_HIGH or
        metrics["cpu_pct"] > CPU_THRESHOLD_HIGH):
        
        new_concurrency = max(MIN_CONCURRENCY, current_concurrency - 1)
        if new_concurrency != current_concurrency:
            logger.info(f"High load detected, reducing concurrency: {current_concurrency} -> {new_concurrency}")
        return new_concurrency
    
    # Check if we can scale UP (low load)
    if (metrics["gpu_mem_pct"] < GPU_MEM_THRESHOLD_LOW and
        metrics["cpu_pct"] < CPU_THRESHOLD_LOW):
        
        new_concurrency = min(MAX_CONCURRENCY, current_concurrency + 1)
        if new_concurrency != current_concurrency:
            logger.info(f"Low load detected, increasing concurrency: {current_concurrency} -> {new_concurrency}")
        return new_concurrency
    
    # Keep current concurrency
    return current_concurrency
