"""Respostas de arquivo com suporte a Range (o pdf.js baixa só os trechos que precisa) e ETag."""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import quote

from django.http import HttpResponse, StreamingHttpResponse

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024
SMALL_FILE = 512 * 1024


def content_disposition(filename: str, attachment: bool) -> str:
    kind = "attachment" if attachment else "inline"
    ascii_name = filename.encode("ascii", "ignore").decode() or "arquivo"
    ascii_name = ascii_name.replace('"', "")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def etag_matches(header: str, etag: str) -> bool:
    """If-None-Match usa comparação fraca e pode trazer vários ETags ou "*" (RFC 9110, seção 13.1.2)."""
    if header.strip() == "*":
        return True
    return etag in {tag.strip().removeprefix("W/") for tag in header.split(",")}


async def _read_async(path: Path, start: int, length: int):
    loop = asyncio.get_running_loop()
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = await loop.run_in_executor(None, handle.read, min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def file_response(
    request,
    path: Path,
    content_type: str,
    filename: str | None = None,
    attachment: bool = False,
    cache_control: str = "private, no-cache",
) -> HttpResponse:
    stat = os.stat(path)
    size = stat.st_size
    etag = f'"{int(stat.st_mtime_ns // 1000)}-{size}"'

    if etag_matches(request.headers.get("If-None-Match", ""), etag):
        response = HttpResponse(status=304)
        response["ETag"] = etag
        response["Cache-Control"] = cache_control
        return response

    start, end, status = 0, size - 1, 200
    header = request.headers.get("Range", "")
    match = RANGE_RE.match(header.strip()) if header else None
    if match and any(match.groups()) and size > 0 and (not request.headers.get("If-Range") or request.headers.get("If-Range") == etag):
        first, last = match.groups()
        if first == "" and last:
            start = max(size - int(last), 0)
        elif first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        if start > end or start >= size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        status = 206

    length = end - start + 1
    if length <= SMALL_FILE:
        with open(path, "rb") as handle:
            handle.seek(start)
            response = HttpResponse(handle.read(length), content_type=content_type, status=status)
    else:
        response = StreamingHttpResponse(_read_async(path, start, length), content_type=content_type, status=status)

    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    response["ETag"] = etag
    response["Cache-Control"] = cache_control
    if status == 206:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    if filename:
        response["Content-Disposition"] = content_disposition(filename, attachment)
    return response
