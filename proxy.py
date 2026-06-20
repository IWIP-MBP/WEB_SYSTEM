import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse

app = FastAPI()

# 定义后端和前端的地址
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:8501"

async def proxy_request(request: Request, target_url: str):
    async with httpx.AsyncClient() as client:
        # 构建转发的 URL
        url = f"{target_url}{request.url.path}"
        if request.url.query:
            url += f"?{request.url.query}"
            
        # 转发请求
        resp = await client.request(
            method=request.method,
            url=url,
            headers=request.headers.raw,
            content=await request.body()
        )
        return StreamingResponse(
            resp.aiter_bytes(),
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path: str):
    if path.startswith("api") or path.startswith("ws"):
        return await proxy_request(request, BACKEND_URL)
    return await proxy_request(request, FRONTEND_URL)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)