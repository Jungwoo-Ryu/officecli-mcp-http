from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from officecli_mcp.core import Settings
from officecli_mcp.server import build_app

TOKEN = "test-token-" + "x" * 40


@pytest.fixture
def settings(tmp_path):
    binary = Path(os.getenv("OFFICECLI_TEST_BINARY", "vendor/officecli/officecli")).resolve()
    if not binary.exists():
        pytest.fail("Install binary with python scripts/download_officecli.py before testing")
    return Settings(token=TOKEN, signing_secret="s" * 48, binary=str(binary), data_dir=tmp_path,
                    max_file_mb=1, _env_file=None)


@pytest.fixture
def running(settings):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    settings.public_base_url = url
    server = uvicorn.Server(uvicorn.Config(build_app(settings), host="127.0.0.1", port=port,
                                          log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(f"{url}/health", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:
        raise RuntimeError("server did not start")
    try:
        yield url, settings
    finally:
        server.should_exit = True
        thread.join(5)
        assert not thread.is_alive()
