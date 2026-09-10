"""Conservative working budgets for machines with 8 GB RAM and small SSDs.

These bound individual caches/buffers, not the process RSS: decoded frames,
calibration masters, Qt, and native libraries need additional memory.
"""

import os

import psutil

MiB = 1024**2
GiB = 1024**3
IMAGE_CACHE_BYTES = 256 * MiB
STACK_MEMORY_BYTES = 256 * MiB
STACK_DISK_BYTES = 8 * GiB
DISK_RESERVE_BYTES = 8 * GiB


def alignment_workers(frame_bytes: int) -> int:
    # Detection has several full-size temporaries. Keep headroom for the GUI,
    # masters and OS; do not multiply native work by every logical CPU.
    available = psutil.virtual_memory().available
    per_worker = max(128 * MiB, frame_bytes * 12)
    return max(1, min(2, os.cpu_count() or 1, available // 3 // per_worker))


def bounded_workers(requested: int, frame_bytes: int, *, copies_per_worker: int = 12) -> int:
    """Resolve automatic/manual parallelism using CPU and available RAM headroom."""
    available = max(1, psutil.virtual_memory().available)
    per_worker = max(128 * MiB, max(1, frame_bytes) * max(2, copies_per_worker))
    memory_limit = max(1, available // 3 // per_worker)
    cpu_limit = max(1, os.cpu_count() or 1)
    desired = cpu_limit if requested <= 0 else requested
    return max(1, min(desired, cpu_limit, memory_limit))
