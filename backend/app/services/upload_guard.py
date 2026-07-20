"""Bounded upload reading — a single guard shared by every upload route.

A Content-Length pre-check can be defeated by HTTP chunked transfer-encoding (no
Content-Length header), so the body must ALSO be read in bounded chunks and
aborted the moment it would exceed the byte budget — otherwise a multi-hundred-MB
chunked body spools to the free Space's small /tmp and is fully materialized in
RAM before any post-read size check.
"""
from fastapi import HTTPException, Request, UploadFile

from .. import config


def reject_oversize_early(request: Request, limit: int | None = None) -> None:
    """Reject on Content-Length BEFORE buffering the body (fast path for honest
    clients). Chunked/absent Content-Length falls through to read_capped."""
    cap = limit if limit is not None else config.MAX_UPLOAD_BYTES
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > cap + 1024 * 1024:
        raise HTTPException(413, f"Upload too large (max {cap // (1024 * 1024)} MB).")


async def read_capped(f: UploadFile, remaining: int) -> bytes:
    """Read an upload part in 1 MB chunks, aborting as soon as it would exceed
    `remaining` bytes. Bounds peak memory regardless of Content-Length honesty."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await f.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > remaining:
            raise HTTPException(413, f"Upload too large (max {remaining // (1024 * 1024)} MB).")
        chunks.append(chunk)
    return b"".join(chunks)
