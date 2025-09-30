from mcp.server.fastmcp import FastMCP
import os, json
import httpx

mcp = FastMCP("wego-mcp-server")

@mcp.tool()
async def get_places_page(
    region_name: str,
    place_type_csv: str,
    page: int = 0,
    size: int = 20,
) -> str:
    """
    Spring /ai/places 호출 → Page JSON 반환
    - 쿠키/헤더 없음
    - placeType은 CSV 그대로 전달 (예: "A01,B01")
    """
    base = os.getenv("SPRING_BASE", "http://localhost:8080").rstrip("/")
    url = f"{base}/ai/places"

    params = {
        "regionName": region_name,
        "placeType": place_type_csv,  # CSV 그대로
        "page": str(page),
        "size": str(size),
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
