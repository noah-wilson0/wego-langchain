import sys, asyncio, json
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

# 환경변수: GOOGLE_API_KEY 가 필요합니다.
# export GOOGLE_API_KEY="..."

# Gemini 2.0 Flash
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")

SYSTEM = (
    "You are a trip planner agent.\n"
    "You MUST use the provided tools to fetch places by page from Spring.\n"
    "Goal: Produce a JSON strictly matching this schema (DraftPlanGeminiRequest):\n"
    "{\n"
    '  "slug": string,\n'
    '  "start_date": "YYYY-MM-DD",\n'
    '  "end_date": "YYYY-MM-DD",\n'
    '  "days": [\n'
    "    {\n"
    '      "date": "YYYY-MM-DD",\n'
    '      "start_time": "HH:mm",\n'
    '      "end_time": "HH:mm",\n'
    '      "places": [{"title": string, "addr": string, "tel": string}],\n'
    '      "accommodation": {"title": string, "addr": string, "tel": string}\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Return ONLY valid JSON (no extra commentary, no code fences).\n"
    "If phone numbers are unavailable, use an empty string for tel."
)

USER_TEMPLATE = (
    "지역 slug={slug}, 지역명={region_name}, 여행일자 {start}~{end}, placeType={place_types}.\n"
    "반드시 MCP tool(get_places_page)을 사용해 /ai/places를 페이징 호출하여 상위 장소를 수집하라.\n"
    "2일 일정 기준으로 각 일자에 2~4개 place와 숙소 1개를 포함하라.\n"
    "모든 필드는 DraftPlanGeminiRequest 스키마로만 출력하고, JSON만 반환하라."
)

async def main():
    # 1) MCP 서버 연결(wego_mcp_server.py를 stdio로 실행)
    client = MultiServerMCPClient({
        "wego": {
            "command": sys.executable,
            "args": ["-u", "wego_mcp_server.py"],
            "transport": "stdio",
            "env": {"PYTHONUNBUFFERED":"1","PYTHONIOENCODING":"utf-8"},
        }
    })
    tools = await client.get_tools()

    # 2) ReAct Agent 구성
    agent = create_react_agent(llm, tools, state_modifier=SYSTEM)

    # 3) 요청 파라미터 예시
    slug = "seoul"
    region_name = "서울"
    start = "2025-10-24"
    end = "2025-10-25"
    place_types = "A01,A02"  # 콤마 구분 권장 (Spring이 자동 split)

    user_msg = USER_TEMPLATE.format(
        slug=slug, region_name=region_name, start=start, end=end, place_types=place_types
    )

    # 4) 실행 (툴 호출 여부는 MCP 서버 콘솔 로그로 확인)
    result = await agent.ainvoke({"messages": [{"role":"user","content": user_msg}]})

    # 5) 최종 응답(JSON 문자열) 꺼내기
    if isinstance(result, dict) and "messages" in result:
        final = result["messages"][-1]["content"]
    else:
        final = str(result)

    cleaned = final.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "").replace("\njson", "").strip("`").strip()

    try:
        plan = json.loads(cleaned)
    except Exception as e:
        print("[WARN] JSON parse failed:", e)
        print("RAW:\n", final)
        return

    # DraftPlanGeminiRequest 형태로 생성된 JSON 출력
    print(json.dumps(plan, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
