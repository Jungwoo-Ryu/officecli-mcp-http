"""Generate a private .env once, refusing to replace existing settings."""
import os
import secrets
from pathlib import Path

path = Path(".env")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write(
        f"OFFICECLI_MCP_TOKEN={secrets.token_urlsafe(48)}\n"
        f"OFFICECLI_MCP_SIGNING_SECRET={secrets.token_urlsafe(48)}\n"
        "OFFICECLI_MCP_PUBLIC_BASE_URL=http://localhost:18080\n"
    )
print("Created .env (mode 0600). Keep it on the server; never commit it.")
