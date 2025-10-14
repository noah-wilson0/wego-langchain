# routers/generate_initial.py
import logging
from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from prompts import SYSTEM_INITIAL, build_initial_user_msg
from models import AutoGenerateInitialRequest, DraftPlanGeminiResponse
from llm import make_mcp_client, make_llm, make_agent
from utils import extract_tools_used, json_from_agent

logger = logging.getLogger(__name__)
router = APIRouter()


def _last_ai_text(messages: list[BaseMessage]) -> str:
    """
    모델의 '마지막 AI 메시지'에서 텍스트를 최대한 복원.
    - ChatGoogleGenerativeAI는 content가 str 이거나 list(dict(type, text))일 수 있음.
    """
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            c = m.content
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts = []
                for p in c:
                    if isinstance(p, dict):
                        # {"type":"text","text":"..."} 형태 지원
                        if p.get("type") == "text" and isinstance(p.get("text"), str):
                            parts.append(p["text"])
                if parts:
                    return "\n".join(parts)
                # 혹시 모를 기타 구조를 문자열화
                return str(c)
            return str(c)
    return ""


@router.post("/ai/generate-initial", response_model=DraftPlanGeminiResponse)
async def generate_initial(req: AutoGenerateInitialRequest):
    """
    v2: AI가 먼저 '아이데이션'으로 일정 구상 → 이후 MCP search_place_by_title로
        모든 아이템 정규화(title→addr/tel) → 최종 JSON 반환
    """
    # 1) MCP 툴 부트스트랩
    client = await make_mcp_client()
    try:
        tools = await client.get_tools()
    except Exception as e:
        logger.exception("MCP bootstrap failed")
        raise HTTPException(status_code=500, detail="MCP bootstrap failed: " + str(e))

    # 2) LLM + 에이전트
    llm = make_llm()
    agent = make_agent(llm, tools, system_prompt=SYSTEM_INITIAL)

    # 3) 프롬프트 빌드(아이데이션 → 정규화 지시 포함)
    user_msg = build_initial_user_msg(
        region_name=req.region_name, start=req.start_date, end=req.end_date,
        day_times=[t.model_dump() for t in (req.day_times or [])]
    )
    msgs = [HumanMessage(content=user_msg)]

    # 4) 1차 실행
    result = await agent.ainvoke({"messages": msgs}, config={"recursion_limit": 80})
    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
    tools_used = extract_tools_used(messages)

    # 5) 툴 미사용 시 1회 강제 재유도 (정규화 단계 보장)
    if "search_place_by_title" not in tools_used:
        enforce = (
            "STOP. You must NORMALIZE every ideated item using the DB via tools before answering.\n"
            f"For EACH item, call: search_place_by_title(region_name='{req.region_name}', "
            "place_type='A01|A02|A03|B01', title='<title>').\n"
            "Return ONLY the final DraftPlanGeminiResponse JSON."
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs}, config={"recursion_limit": 80})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

    # ⭐ 파싱/검증 직전 '원문' 로깅
    raw_text = _last_ai_text(messages)
    logger.exception("[ai.generate-initial] RAW_MODEL_OUTPUT:\n%s", raw_text)

    # 6) 최종 JSON 파싱/검증
    try:
        plan_dict = json_from_agent(messages)  # 내부에서 json.loads 수행 가정
        plan = DraftPlanGeminiResponse(**plan_dict)
    except Exception as e:
        # 응답 detail에도 앞부분만 넣어 디버깅 편의 제공
        preview = (raw_text[:1200] + "...(truncated)") if raw_text and len(raw_text) > 1200 else raw_text
        logger.exception("Invalid plan JSON. Error=%s\nRAW PREVIEW:\n%s", e, preview)
        raise HTTPException(status_code=400, detail=f"Invalid plan JSON: {e}. RAW_PREVIEW:\n{preview}")

    logger.info("[initial plans]: %s", plan)
    return plan.model_dump()
