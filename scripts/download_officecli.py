"""Download a pinned official OfficeCLI binary and verify the release SHA-256."""
from __future__ import annotations

import hashlib
import os
import platform
import sys
import urllib.request
from pathlib import Path

VERSION = "1.0.158"
ASSETS = {
    "x86_64": ("x64", "9ee41d5558caea7bcd5aab1b3e76b2bd70f0535f09cf65dda3668130510cc719"),
    "aarch64": ("arm64", "b1d5e74d93a8471a47b037cc7774ac29c559940e226f99b9fdf788966cc395b8"),
}


def main():
    arch, expected = ASSETS[platform.machine()]
    url = f"https://github.com/iOfficeAI/OfficeCLI/releases/download/v{VERSION}/officecli-linux-{arch}"
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "vendor/officecli/officecli")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit("OfficeCLI SHA-256 verification failed")
    destination.write_bytes(data)
    os.chmod(destination, 0o755)
    print(f"OfficeCLI v{VERSION} ({arch}): checksum verified")


if __name__ == "__main__":
    main()
