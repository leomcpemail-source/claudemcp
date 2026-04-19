import asyncio
import os
import base64
from typing import Optional
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

# GitHub API setup
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# สร้าง MCP Server
server = Server("github-mcp")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_repos",
            description="แสดงรายการ repositories ทั้งหมด",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "default": "leomcpemail-source"},
                    "per_page": {"type": "integer", "default": 30}
                }
            }
        ),
        Tool(
            name="get_file_content",
            description="อ่านเนื้อหาไฟล์จาก repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "username/repo-name"},
                    "path": {"type": "string"},
                    "branch": {"type": "string", "default": "main"}
                },
                "required": ["repo", "path"]
            }
        ),
        Tool(
            name="create_or_update_file",
            description="สร้างหรืออัพเดทไฟล์ใน repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "message": {"type": "string"},
                    "branch": {"type": "string", "default": "main"}
                },
                "required": ["repo", "path", "content", "message"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_repos":
        username = arguments.get("username", "leomcpemail-source")
        per_page = arguments.get("per_page", 30)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/users/{username}/repos?per_page={per_page}&sort=updated",
                headers=HEADERS,
                timeout=30.0
            )
            if resp.status_code != 200:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
            
            repos = resp.json()
            result = "\n".join([f"- {r['name']}: {r['html_url']}" for r in repos])
            return [TextContent(type="text", text=result)]
    
    elif name == "get_file_content":
        repo = arguments["repo"]
        path = arguments["path"]
        branch = arguments.get("branch", "main")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
                headers=HEADERS,
                timeout=30.0
            )
            if resp.status_code != 200:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
            
            data = resp.json()
            if data.get("encoding") == "base64" and data.get("content"):
                content = base64.b64decode(data["content"]).decode('utf-8')
                return [TextContent(type="text", text=content)]
            
            return [TextContent(type="text", text="Cannot decode file")]
    
    elif name == "create_or_update_file":
        repo = arguments["repo"]
        path = arguments["path"]
        content = arguments["content"]
        message = arguments["message"]
        branch = arguments.get("branch", "main")
        
        async with httpx.AsyncClient() as client:
            # Get SHA if exists
            sha = None
            try:
                file_resp = await client.get(
                    f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
                    headers=HEADERS,
                    timeout=30.0
                )
                if file_resp.status_code == 200:
                    sha = file_resp.json()["sha"]
            except:
                pass
            
            payload = {
                "message": message,
                "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
                "branch": branch
            }
            if sha:
                payload["sha"] = sha
            
            resp = await client.put(
                f"https://api.github.com/repos/{repo}/contents/{path}",
                headers=HEADERS,
                json=payload,
                timeout=30.0
            )
            
            if resp.status_code in [200, 201]:
                return [TextContent(type="text", text="File updated successfully")]
            else:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
    
    return [TextContent(type="text", text="Unknown tool")]

# สร้าง Starlette app
async def handle_sse(request):
    transport = SseServerTransport("/messages")
    await server.run(
        transport.read_stream,
        transport.write_stream,
        server.create_initialization_options()
    )

app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
    ]
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
