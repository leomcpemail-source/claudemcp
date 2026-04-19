from fastmcp import FastMCP
import httpx
import os
import base64
from typing import Optional

mcp = FastMCP("GitHub MCP")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

@mcp.tool()
async def list_repos(username: str = "leomcpemail-source", per_page: int = 30):
    """แสดงรายการ repositories ทั้งหมด"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/users/{username}/repos?per_page={per_page}&sort=updated",
            headers=HEADERS,
            timeout=30.0
        )
        if resp.status_code != 200:
            return {"error": resp.text}
        
        repos = resp.json()
        return [{
            "name": r["name"],
            "full_name": r["full_name"],
            "url": r["html_url"],
            "description": r.get("description", ""),
            "updated_at": r["updated_at"],
            "default_branch": r["default_branch"]
        } for r in repos]

@mcp.tool()
async def get_file_content(repo: str, path: str, branch: str = "main"):
    """อ่านเนื้อหาไฟล์จาก repository"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
            headers=HEADERS,
            timeout=30.0
        )
        if resp.status_code != 200:
            return {"error": resp.text}
        
        data = resp.json()
        
        if data.get("encoding") == "base64" and data.get("content"):
            try:
                content = base64.b64decode(data["content"]).decode('utf-8')
                return {
                    "name": data["name"],
                    "path": data["path"],
                    "sha": data["sha"],
                    "size": data["size"],
                    "content": content,
                    "url": data["html_url"]
                }
            except:
                return {"error": "Cannot decode file content (might be binary)"}
        
        return data

@mcp.tool()
async def create_or_update_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
    sha: Optional[str] = None
):
    """สร้างหรืออัพเดทไฟล์ใน repository"""
    async with httpx.AsyncClient() as client:
        if not sha:
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
        
        if resp.status_code not in [200, 201]:
            return {"error": resp.text}
        
        result = resp.json()
        return {
            "status": "success",
            "commit_sha": result["commit"]["sha"],
            "file_url": result["content"]["html_url"]
        }

@mcp.tool()
async def delete_file(
    repo: str,
    path: str,
    message: str,
    branch: str = "main",
    sha: Optional[str] = None
):
    """ลบไฟล์จาก repository"""
    async with httpx.AsyncClient() as client:
        if not sha:
            file_resp = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}",
                headers=HEADERS,
                timeout=30.0
            )
            if file_resp.status_code != 200:
                return {"error": "File not found"}
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
        
        if resp.status_code != 200:
            return {"error": resp.text}
        
        return {"status": "deleted", "commit": resp.json()["commit"]["sha"]}

@mcp.tool()
async def list_branches(repo: str):
    """แสดงรายการ branches ทั้งหมด"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/branches",
            headers=HEADERS,
            timeout=30.0
        )
        if resp.status_code != 200:
            return {"error": resp.text}
        
        branches = resp.json()
        return [{"name": b["name"], "sha": b["commit"]["sha"]} for b in branches]

@mcp.tool()
async def trigger_pages_build(repo: str):
    """Trigger GitHub Pages rebuild"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{repo}/pages/builds",
            headers=HEADERS,
            timeout=30.0
        )
        if resp.status_code not in [200, 201]:
            return {"error": resp.text}
        
        return {"status": "Pages build triggered"}

@mcp.tool()
async def get_latest_commit(repo: str, branch: str = "main"):
    """ดึงข้อมูล commit ล่าสุด"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/commits/{branch}",
            headers=HEADERS,
            timeout=30.0
        )
        if resp.status_code != 200:
            return {"error": resp.text}
        
        data = resp.json()
        return {
            "sha": data["sha"],
            "message": data["commit"]["message"],
            "author": data["commit"]["author"]["name"],
            "date": data["commit"]["author"]["date"],
            "url": data["html_url"]
        }

@mcp.tool()
async def list_repo_contents(repo: str, path: str = "", branch: str = "main"):
    """แสดงรายการไฟล์และโฟลเดอร์ใน repository"""
    async with httpx.AsyncClient() as client:
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        if branch:
            url += f"?ref={branch}"
        
        resp = await client.get(url, headers=HEADERS, timeout=30.0)
        if resp.status_code != 200:
            return {"error": resp.text}
        
        items = resp.json()
        if isinstance(items, list):
            return [{
                "name": item["name"],
                "path": item["path"],
                "type": item["type"],
                "size": item.get("size", 0),
                "url": item["html_url"]
            } for item in items]
        else:
            return items

# รัน server ในโหมด SSE สำหรับ Render
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.get_asgi_app(), host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
