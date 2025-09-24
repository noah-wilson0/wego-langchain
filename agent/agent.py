import os, json, random, re
from typing import List, Dict, Any
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()
MCP_BASE = os.getenv("MCP_BASE", "http://localhost:4000")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def tool_get_places_by_city_slug(params_json: str) -> str:
    p = json.loads(params_json)
    r = requests.get(f"{MCP_BASE}/tools/places/by_city_slug", params=p, timeout=60)
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text}"
    return r.text

tools = [Tool(
    name="places_by_city_slug",
    func=tool_get_places_by_city_slug,
    description='예: {"slug":"jeju","types":"A01,A02,A03,B01","limit":80,"offset":0,"order":"rating_desc"}'
)]

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.2,
    max_output_tokens=4096,
    google_api_key=GOOGLE_API_KEY,
)

class PlaceOut(BaseModel):
    title: str
    addr: str | None = None
    tel: str | None = None

class DayOut(BaseModel):
    date: str
    start_time: str
    end_time: str
    places: List[PlaceOut]
    accommodations: List[PlaceOut] = Field(default_factory=list)

class ItineraryOut(BaseModel):
    start_date: str
    end_date: str
    days: List[DayOut]

FINAL_PLAN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a travel planner. Build a JSON object strictly matching this schema:\n"
     "{schema}\nRules:\n"
     "- Use ONLY the given allowed_places list to fill titles/addr/tel.\n"
     "- If accommodations are included, choose items with place_type 'B01'.\n"
     "- Dates: {start_date} ~ {end_date}\n"
     "- Time window: {daily_start} ~ {daily_end}\n"
     "- Route: {route_type}\n"
     "- Output must be PURE JSON (no markdown/code fences/text)."),
    ("human",
     "ALLOWED_PLACES (from DB):\n{allowed_places_json}\n\n"
     "User request: {user_request}\n"
     "Return ONLY valid JSON.")
])

def shortlist_allowed_places_for_city(
    slug: str,
    pages: int = 4, limit: int = 80, per_page_pick: int = 40,
    types: str = "A01,A02,A03,B01"
) -> List[Dict[str, Any]]:
    picked: list[Dict[str, Any]] = []
    offset = 0
    for _ in range(pages):
        payload = {"slug": slug, "types": types, "limit": limit, "offset": offset, "order": "rating_desc"}
        page_text = tool_get_places_by_city_slug(json.dumps(payload))

        # 기본값(안전 초기화)
        page: Dict[str, Any] = {}
        items: List[Dict[str, Any]] = []

        # 응답 파싱
        try:
            # MCP가 "HTTP 404: ..." 같은 문자열을 돌려줄 수도 있으니 방어
            if isinstance(page_text, str) and page_text.startswith("HTTP "):
                print(f"[WARN] MCP error: {page_text}")
            else:
                page = json.loads(page_text)
                items = page.get("items", []) if isinstance(page, dict) else []
        except Exception as e:
            print(f"[WARN] JSON parse failed: {e}; raw={page_text[:200]}")

        # 아이템이 없으면 루프 종료
        if not items:
            break

        # 상위 일부 + 약간 샘플링
        head = items[:per_page_pick]
        tail = (
            random.sample(items[per_page_pick:], k=min(10, max(0, len(items) - per_page_pick)))
            if len(items) > per_page_pick else []
        )
        picked.extend(head + tail)

        # 다음 페이지
        next_offset = page.get("next_offset") if isinstance(page, dict) else None
        if not next_offset:
            break
        offset = next_offset

    # place_id 기준 dedup
    seen = set(); dedup: List[Dict[str, Any]] = []
    for it in picked:
        pid = it.get("place_id")
        if pid in seen:
            continue
        seen.add(pid); dedup.append(it)

    return dedup[:160] if len(dedup) > 160 else dedup


def _parse_llm_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE|re.DOTALL).strip()
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m: raise ValueError("No JSON object found in LLM output.")
    return json.loads(m.group(0))

def build_itinerary_from_allowed_places(
    allowed_places: List[Dict[str, Any]],
    start_date: str, end_date: str,
    route_type: str, daily_start: str, daily_end: str,
    user_request: str
) -> ItineraryOut:
    schema_text = json.dumps(ItineraryOut.model_json_schema(), indent=2)
    messages = FINAL_PLAN_PROMPT.format_messages(
        schema=schema_text, start_date=start_date, end_date=end_date,
        daily_start=daily_start, daily_end=daily_end, route_type=route_type,
        allowed_places_json=json.dumps(allowed_places, ensure_ascii=False),
        user_request=user_request
    )
    text = llm.invoke(messages).content.strip()
    print("DEBUG LLM OUTPUT >>>"); print(text); print("<<< END LLM OUTPUT")
    data = _parse_llm_json(text)
    return ItineraryOut(**data)

if __name__ == "__main__":
    # 예시: 제주 slug (city_slug에 꼭 있어야 함)
    slug = "jeju"            # ← 원하는 지역 slug로 변경 (예: gangneung, geoje, donghae-samcheok)
    allowed = shortlist_allowed_places_for_city(slug, pages=4, limit=80, per_page_pick=40, types="A01,A02,A03,B01")
    itin = build_itinerary_from_allowed_places(
        allowed_places=allowed,
        start_date="2025-10-16", end_date="2025-10-18",
        route_type="transit", daily_start="09:00", daily_end="20:00",
        user_request="먹거리/자연/카페 균형 있게."
    )
    print(itin.model_dump())
