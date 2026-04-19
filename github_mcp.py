import os
import base64
import asyncio
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from sse_starlette import EventSourceResponse
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
        ),
        Tool(
            name="list_branches",
            description="แสดงรายการ branches ทั้งหมด",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"}
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="delete_file",
            description="ลบไฟล์จาก repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "message": {"type": "string"},
                    "branch": {"type": "string", "default": "main"}
                },
                "required": ["repo", "path", "message"]
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
            result = "\n".join([f"- {r['name']}: {r['html_url']}" for r in repos[:10]])
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
                result = resp.json()
                return [TextContent(
                    type="text", 
                    text=f"✅ File {path} updated successfully\nCommit: {result['commit']['sha']}\nURL: {result['content']['html_url']}"
                )]
            else:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
    
    elif name == "delete_file":
        repo = arguments["repo"]
        path = arguments["path"]
        message = arguments["message"]
        branch = arguments.get("branch", "main")
        
        async with httpx.AsyncClient() as client:
            file_resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
                headers=HEADERS,
                timeout=30.0
            )
            if file_resp.status_code != 200:
                return [TextContent(type="text", text="Error: File not found")]
            
            sha = file_resp.json()["sha"]
            
            resp = await client.delete(
                f"https://api.github.com/repos/{repo}/contents/{path}",
                headers=HEADERS,
                json={
                    "message": message,
                    "sha": sha,
                    "branch": branch
                },
                timeout=30.0
            )
            
            if resp.status_code == 200:
                return [TextContent(type="text", text=f"✅ File {path} deleted successfully")]
            else:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
    
    elif name == "list_branches":
        repo = arguments["repo"]
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/branches",
                headers=HEADERS,
                timeout=30.0
            )
            if resp.status_code != 200:
                return [TextContent(type="text", text=f"Error: {resp.text}")]
            
            branches = resp.json()
            result = "\n".join([f"- {b['name']}" for b in branches])
            return [TextContent(type="text", text=result)]
    
    return [TextContent(type="text", text="Unknown tool")]

# SSE endpoint สำหรับ Claude
async def handle_sse(request):
    """Handle SSE connection from Claude.ai"""
    
    async def event_generator():
        # Send keepalive ping every 15 seconds
        try:
            while True:
                # SSE format
                yield "event: ping\ndata: {}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass
    
    return EventSourceResponse(event_generator())

# Health check endpoint
async def health_check(request):
    from starlette.responses import JSONResponse
    return JSONResponse({
        "status": "healthy",
        "service": "github-mcp",
        "tools": len(await list_tools())
    })

app = Starlette(
    routes=[
        Route("/", endpoint=health_check),
        Route("/health", endpoint=health_check),
        Route("/sse", endpoint=handle_sse),
    ]
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"Starting GitHub MCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
