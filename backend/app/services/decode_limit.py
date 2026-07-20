"""Process-wide concurrency cap on heavy DICOM/image decodes.

The per-IP rate limiter bounds request RATE, not in-flight CONCURRENCY: many small
requests (or a burst from a few IPs) can each dispatch a big transient decode to the
threadpool and collectively OOM the box. This wraps those decodes in a shared
semaphore so at most MAX_CONCURRENT_DECODES run at once; excess requests wait (and are
still bounded by the request timeout / rate limiter). Use for every untrusted-DICOM
decode (viewer, ROI, segmentation, analyze).
"""
import asyncio

from fastapi.concurrency import run_in_threadpool

from .. import config

_sem = asyncio.Semaphore(config.MAX_CONCURRENT_DECODES)


async def heavy(func, *args, **kwargs):
    """Run a CPU/memory-heavy decode in the threadpool under the shared semaphore."""
    async with _sem:
        return await run_in_threadpool(func, *args, **kwargs)
