# main.py (FastAPI)
import os, json, sys, traceback
from typing import Any, Dict, List
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("환경변수 GOOGLE_API_KEY 없음")

SERVER_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "wego_mcp_server.py"))
if not os.path.exists(SERVER_SCRIPT):
    raise RuntimeError(f"MCP server not found: {SERVER_SCRIPT}")

# ===== DraftPlanGeminiResponse 스키마 =====
class Place(BaseModel):
    title: str
    addr: str
    tel: str

class Accommodation(BaseModel):
    title: str
    addr: str
    tel: str

class DayItem(BaseModel):
    date: str
    start_time: str
    end_time: str
    places: List[Place]
    accommodation: Accommodation

class DraftPlanGeminiResponse(BaseModel):
    label: str
    start_date: str
    end_date: str
    days: List[DayItem]

# 요청 바디 (Spring -> FastAPI)
class AutoGenerateInitialRequest(BaseModel):
    member_id: int
    region_name: str
    start_date: str
    end_date: str
    chemi: Dict[str, Any] = Field(default_factory=dict)

# ===== 에이전트 시스템 프롬프트 =====
# → 툴을 모르면 장소를 모른다고 못박고, 반드시 get_places_page를 먼저 호출하게 강제
SYSTEM = (
    "You are a trip planner agent.\n"
    "You DO NOT know any places unless you call tools.\n"
    "You MUST call the MCP tool `get_places_page` for each category BEFORE producing the final JSON.\n"
    "- Call it separately for A01(명소), A02(음식점), A03(카페), and B01(숙소).\n"
    "- Use page=0 first; if not enough items, also use page=1.\n"
    "\n"
    "Daily composition **must** satisfy:\n"
    "- At least 2 A01(명소)\n"
    "- At least 2 A02(음식점)\n"
    "- At least 1 A03(카페)\n"
    "- Exactly 1 B01(숙소) (You may reuse the same accommodation for all days.)\n"
    "\n"
    "Mapping rule:\n"
    "- For each selected place, fill {\"title\", \"addr\", \"tel\"}; if tel is unknown, use an empty string \"\".\n"
    "- Prefer non-duplicate places across the whole trip; if inventory is insufficient, allow duplicates as a last resort.\n"
    "\n"
    "After observing tool outputs, produce ONLY a valid DraftPlanGeminiResponse JSON (no extra text):\n"
    "{\n"
    '  \"label\": string,\n'
    '  \"start_date\": \"YYYY-MM-DD\",\n'
    '  \"end_date\": \"YYYY-MM-DD\",\n'
    '  \"days\": [\n'
    "    {\n"
    '      \"date\": \"YYYY-MM-DD\",\n'
    '      \"start_time\": \"HH:mm\",\n'
    '      \"end_time\": \"HH:mm\",\n'
    '      \"places\": [{\"title\": string, \"addr\": string, \"tel\": string}],\n'
    '      \"accommodation\": {\"title\": string, \"addr\": string, \"tel\": string}\n'
    "    }\n"
    "  ]\n"
    "}\n"
)


# 사용자 지시: 먼저 page=0 호출, 필요 시 page=1 호출 후 최종 JSON만 출력
USER_TEMPLATE = (
    "지역 label={label}, 지역명={region_name}, 여행일자 {start}~{end}.\n"
    "아래 순서로 MCP tool(get_places_page)을 호출해 데이터 수집 후 일정을 구성해.\n"
    "1) 명소(A01): get_places_page(region_name={region_name}, place_type_csv='A01', page=0, size=40) → 부족하면 page를 추가로 호출\n"
    "2) 음식점(A02): get_places_page(region_name={region_name}, place_type_csv='A02', page=0, size=40) → 부족하면를 추가로 호출\n"
    "3) 카페(A03): get_places_page(region_name={region_name}, place_type_csv='A03', page=0, size=40) → 부족하면를 추가로 호출\n"
    "4) 숙소(B01): get_places_page(region_name={region_name}, place_type_csv='B01', page=0, size=40) → 부족하면를 추가로 호출\n"
    "\n"
    "배치 규칙(각 일자):\n"
    "- A01(명소) 최소 2개, A02(음식점) 최소 2개, A03(카페) 최소 1개를 places 배열에 포함\n"
    "- B01(숙소) 1개를 accommodation에 설정(모든 일정에 동일 숙소 사용 가능)\n"
    "- tel 값이 없으면 빈 문자열(\"\") 사용\n"
    "- 가능한 한 전체 일정에서 중복을 피하되, 수량이 부족하면 중복 허용\n"
    "- label에는 label이외의 문자를 쓰지않는다.\n"
    "\n"
    "마지막으로 DraftPlanGeminiResponse JSON만 출력."
)


app = FastAPI()

def _extract_tools_used(messages: Any) -> List[str]:
    """
    LangGraph result['messages']에서 MCP 툴 호출 흔적 수집.
    - additional_kwargs.tool_calls (OpenAI 유사 포맷)
    - ToolMessage.name
    - content 문자열 내 함수명 폴백
    """
    used = set()
    try:
        for m in messages:
            # tool_calls 포맷
            ak = getattr(m, "additional_kwargs", {}) or {}
            for tc in ak.get("tool_calls", []):
                name = (tc.get("function") or {}).get("name")
                if name:
                    used.add(name)
            # ToolMessage.name
            name_attr = getattr(m, "name", None)
            if name_attr:
                used.add(name_attr)
            # 텍스트 폴백
            content = str(getattr(m, "content", ""))
            if "get_places_page" in content:
                used.add("get_places_page")
    except Exception:
        pass
    return sorted(used)

@app.post("/ai/generate-initial", response_model=DraftPlanGeminiResponse)
async def generate_initial(req: AutoGenerateInitialRequest):
    print(f"[FastAPI] Spawning MCP: {sys.executable} -u {SERVER_SCRIPT}", file=sys.stderr, flush=True)
    print(f"[FastAPI] MCP ENV: {{'SPRING_BASE': {os.getenv('SPRING_BASE')}}}", file=sys.stderr, flush=True)

    # 0) MCP 서버 연결 (stdio)
    client = MultiServerMCPClient({
        "wego": {
            "command": sys.executable,
            "args": ["-u", SERVER_SCRIPT],
            "transport": "stdio",
            "env": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "SPRING_BASE": os.getenv("SPRING_BASE", "http://localhost:8080"),
            },
        }
    })
    try:
        tools = await client.get_tools()
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"MCP bootstrap failed: {e}\n{tb}")

    # 1) LLM/에이전트
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=GOOGLE_API_KEY)
    agent = create_react_agent(llm, tools, prompt=SYSTEM)

    # 2) 사용자 메시지
    label_guess = req.region_name.lower()
    place_types = "A01,A02,A03,B01"  # 필요 시 조정
    user_msg = USER_TEMPLATE.format(
        label=label_guess,
        region_name=req.region_name,
        start=req.start_date,
        end=req.end_date,
        place_types=place_types,
    )

    # 3) 1차 실행
    msgs = [HumanMessage(content=user_msg)]
    result = await agent.ainvoke({"messages": msgs})

    # 4) 툴 사용 여부 체크
    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
    tools_used = _extract_tools_used(messages)

    # 5) 툴 미사용 시 1회 강제 재시도
    if "get_places_page" not in tools_used:
        enforce = (
            "DO NOT answer yet.\n"
            "First, call get_places_page NOW with exactly:\n"
            f'{{"region_name":"{req.region_name}","place_type_csv":"{place_types}","page":0,"size":20}}\n'
            "Return the Observation and then the final DraftPlanGeminiResponse JSON."
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
        tools_used = _extract_tools_used(messages)

    # 6) 최종 텍스트 추출
    final_msg = next((m for m in reversed(messages) if getattr(m, "content", None)), None)
    if final_msg is None:
        raise HTTPException(status_code=500, detail="Agent returned no final text message.")
    final = str(final_msg.content).strip()

    # 7) 코드블록 제거 및 JSON 파싱
    if final.startswith("```"):
        final = final.strip("`")
        final = final.replace("json\n", "").replace("\njson", "").strip("`").strip()

    try:
        plan_dict = json.loads(final)
        plan = DraftPlanGeminiResponse(**plan_dict)
    except Exception as e:
        print("[FastAPI] JSON parse failed:", e, flush=True)
        print("RAW:\n", final, flush=True)
        raise HTTPException(status_code=400, detail=f"Invalid plan JSON: {e}")

    # 8) 최종 응답 (툴 사용 내역 포함)
    return plan.model_dump()  # pydantic v2 권장 (v1이면 plan.dict())

if __name__ == "__main__":
    uvicorn.run("main:app", port=7070)
