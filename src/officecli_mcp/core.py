from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from weakref import WeakValueDictionary
from zipfile import BadZipFile, ZipFile

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    token: str = Field(min_length=32)
    signing_secret: str = Field(min_length=32)
    data_dir: Path = Path("/data")
    binary: str = "officecli"
    public_base_url: str = "http://localhost:18080"
    host: str = "0.0.0.0"
    port: int = 8080
    max_file_mb: int = Field(default=25, ge=1, le=100)
    command_timeout: int = Field(default=60, ge=1, le=300)
    download_ttl: int = Field(default=900, ge=1, le=86400)
    allowed_hosts: str = "localhost:*,127.0.0.1:*,officecli-mcp:*"
    model_config = SettingsConfigDict(env_prefix="OFFICECLI_MCP_", env_file=".env", extra="ignore")


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self.process_slots = asyncio.Semaphore(4)

    def lock(self, user: str) -> asyncio.Lock:
        # No await between lookup and insert: creation is atomic on this event loop.
        if user not in self._locks:
            self._locks[user] = lock = asyncio.Lock()
            return lock
        return self._locks[user]

    def path(self, user: str, filename: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", user):
            raise ValueError("invalid user ID")
        if (not filename or filename.startswith(".") or "/" in filename or "\\" in filename
            or any(ord(c) < 32 for c in filename) or len(filename.encode()) > 240
            or Path(filename).suffix.lower() not in {".docx", ".xlsx"}):
            raise ValueError("filename must be a .docx/.xlsx basename without path components")
        directory = self.root / user
        directory.mkdir(exist_ok=True)
        resolved = directory.resolve()
        if resolved != directory or not resolved.is_relative_to(self.root):
            raise ValueError("invalid user directory")
        target = directory / filename
        if target.is_symlink() or target.resolve().parent != directory:
            raise ValueError("invalid file path")
        return target

    @property
    def max_bytes(self) -> int:
        return self.settings.max_file_mb * 1024 * 1024

    def validate(self, data: bytes, filename: str) -> None:
        if len(data) > self.max_bytes:
            raise OverflowError("file too large")
        member = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml"}[Path(filename).suffix.lower()]
        try:
            with ZipFile(BytesIO(data)) as archive:
                infos = archive.infolist()
                names = {i.filename for i in infos}
                if "[Content_Types].xml" not in names or member not in names:
                    raise ValueError("file contents do not match extension")
                if len(infos) > 10000 or sum(i.file_size for i in infos) > self.max_bytes * 10:
                    raise ValueError("Office archive expansion exceeds limit")
                if any(i.flag_bits & 1 for i in infos):
                    raise ValueError("encrypted archives are unsupported")
                if any(n.lower().endswith("vbaproject.bin") for n in names):
                    raise ValueError("macro-enabled files are unsupported")
        except BadZipFile as exc:
            raise ValueError("invalid Office ZIP package") from exc

    def write(self, path: Path, data: bytes) -> None:
        self.validate(data, path.name)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(data)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def metadata(self, user: str, filename: str) -> dict:
        path = self.path(user, filename)
        expiry = int(time.time()) + self.settings.download_ttl
        body = base64.urlsafe_b64encode(json.dumps([user, filename, expiry], ensure_ascii=False).encode()).decode().rstrip("=")
        signature = hmac.new(self.settings.signing_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return {"filename": filename, "size_bytes": path.stat().st_size,
                "download_url": f"{self.settings.public_base_url.rstrip('/')}/files/{body}.{signature}",
                "download_expires_at": expiry}

    def verify(self, token: str) -> Path:
        try:
            body, signature = token.rsplit(".", 1)
            expected = hmac.new(self.settings.signing_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid signature")
            user, filename, expiry = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if not isinstance(expiry, int) or expiry <= time.time():
                raise ValueError("expired download")
            return self.path(user, filename)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValueError("invalid or expired download token") from exc

    async def run(self, *arguments: str) -> dict:
        env = {**os.environ, "OFFICECLI_NO_AUTO_RESIDENT": "1", "OFFICECLI_SKIP_UPDATE": "1"}
        async with self.process_slots:
            proc = await asyncio.create_subprocess_exec(
                self.settings.binary, *arguments, "--json", env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), self.settings.command_timeout)
            except BaseException:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
                raise
        text = stdout.decode(errors="replace")
        try:
            result = json.loads(text)
        except ValueError:
            result = {"text": text[:100000]}
        if proc.returncode not in {0, 2} or (isinstance(result, dict) and result.get("success") is False):
            raise ValueError(f"OfficeCLI command failed: {json.dumps(result, ensure_ascii=False)[:4000]} {stderr.decode(errors='replace')[:1000]}")
        return {"exit_code": proc.returncode, "result": result}


def disposition(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
