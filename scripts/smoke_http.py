"""Real MCP + attachment roundtrip against a running Docker container."""
from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    load_dotenv()
    base = os.getenv("OFFICECLI_MCP_URL", "http://localhost:18080/mcp").removesuffix("/mcp")
    auth = {"Authorization": f"Bearer {os.environ['OFFICECLI_MCP_TOKEN']}", "X-User-Id": f"smoke-{uuid4().hex[:12]}"}
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.post("/mcp", json={})).status_code == 401
        async with (
            streamablehttp_client(f"{base}/mcp", headers=auth) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            async def call(name, **args):
                result = await session.call_tool(name, args)
                assert not result.isError, result
                return result.structuredContent or json.loads(result.content[0].text)

            created = await call("office_create", filename="보고서.docx", operations=[
                {"action": "add", "path": "/body", "element_type": "paragraph", "props": {"text": "첨부 원본"}},
            ])
            data = (await http.get(created["download_url"])).content
            uploaded = await http.post("/api/files", headers=auth, files={"file": ("첨부.docx", data)})
            assert uploaded.status_code == 201, uploaded.text
            changed = await call("office_edit", filename="첨부.docx", operations=[
                {"action": "set", "path": "/body/p[1]", "props": {"text": "수정 성공"}},
            ])
            text = await call("office_read", filename=changed["filename"])
            assert "수정 성공" in json.dumps(text, ensure_ascii=False)
            assert (await http.get(changed["download_url"])).status_code == 200
            assert (await http.get("/api/files/첨부.docx", headers=auth)).content == data
            assert (await http.get("/api/files/첨부.docx", headers={**auth, "X-User-Id": "other-user"})).status_code == 404
            book = await call("office_create", filename="예산.xlsx", operations=[
                {"action": "set", "path": "/Sheet1/A1", "props": {"value": 10}},
                {"action": "set", "path": "/Sheet1/B1", "props": {"formula": "A1*2"}},
            ])
            book_data = (await http.get(book["download_url"])).content
            uploaded = await http.put("/api/files/첨부.xlsx", headers=auth, content=book_data)
            assert uploaded.status_code == 201
            changed = await call("office_edit", filename="첨부.xlsx", operations=[
                {"action": "set", "path": "/Sheet1/A1", "props": {"value": 30}},
            ])
            cell = await call("office_get", filename=changed["filename"], path="/Sheet1/B1")
            assert cell["result"]["data"]["results"][0]["format"]["computedValue"] == "60"
    print("PASS: Streamable HTTP, auth, DOCX/XLSX create + attachment edit + download, original preservation, user isolation")


if __name__ == "__main__":
    asyncio.run(main())
