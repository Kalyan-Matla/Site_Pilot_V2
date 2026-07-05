"""File storage abstraction: local disk (dev / Docker / Render) or Vercel
Blob (when BLOB_READ_WRITE_TOKEN is set — needed on Vercel, where the
deployed filesystem is read-only/ephemeral and nothing written to it
survives past the current request).

Callers only ever see one opaque "handle" string per file, which is exactly
what's stored in file_path columns: a relative filename for local disk, or a
full https:// URL for Blob. download_response() branches on that prefix so
neither documents.py nor projects.py needs to know which backend is active.
"""
import logging
import os

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from .db import UPLOAD_DIR

log = logging.getLogger("sitepilot.storage")

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN")
# Vercel Functions reject request bodies over 4.5 MB before our code ever
# runs, so cap well under that when Blob (i.e. Vercel) is in play.
MAX_UPLOAD = int(os.environ.get(
    "MAX_UPLOAD_BYTES", str(4 * 1024 * 1024) if BLOB_TOKEN else str(25 * 1024 * 1024)))


def _is_url(handle: str) -> bool:
    return handle.startswith("http://") or handle.startswith("https://")


def save_file(data: bytes, pathname: str) -> str:
    """Stores `data` and returns its handle. Raises 413 over MAX_UPLOAD."""
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"File exceeds the {MAX_UPLOAD // (1024 * 1024)} MB upload limit")
    if BLOB_TOKEN:
        try:
            import vercel_blob
            resp = vercel_blob.put(pathname, data, addRandomSuffix="true")
            url = resp["url"] if isinstance(resp, dict) else resp.url
            if url:
                return url
            log.warning("vercel_blob.put returned no url for %s; falling back to local disk", pathname)
        except Exception:
            log.exception("vercel_blob upload failed for %s; falling back to local disk", pathname)
    dest = UPLOAD_DIR / pathname
    dest.write_bytes(data)
    return dest.name


def download_response(handle: str, filename: str | None = None):
    """Redirects to the Blob URL, or serves the local file — same call site
    either way."""
    if _is_url(handle):
        return RedirectResponse(handle, status_code=307)
    path = UPLOAD_DIR / handle
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename or handle)


def delete_file(handle: str):
    """Best-effort delete; failures here shouldn't block deleting the DB row."""
    if _is_url(handle):
        if not BLOB_TOKEN:
            return
        try:
            import vercel_blob
            vercel_blob.delete([handle])
        except Exception:
            log.exception("vercel_blob delete failed for %s", handle)
        return
    (UPLOAD_DIR / handle).unlink(missing_ok=True)
