from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from models import (
    DraftPlanCorrectionRequest,
    DraftPlanCorrectedPlaceResponse,
    DraftPlanGeminiResponse,
)
from prompts import SYSTEM_REPAIR, build_repair_user_msg
from llm import make_mcp_client, make_llm, make_agent
from utils import extract_tools_used, json_from_agent

router = APIRouter()

def _is_accommodation_slot(plan: DraftPlanGeminiResponse, correction: DraftPlanCorrectionRequest.CorrectionPlace) -> bool:
    # accommodation과 title/addr/tel이 일치(느슨 비교)하면 숙소교체로 간주
    target_title = correction.title.strip().lower()
    for d in plan.days:
        if d.accommodation:
            if d.accommodation.title.strip().lower() == target_title:
                return True
    return False

def _used_titles(plan: DraftPlanGeminiResponse, exclude: str) -> list[str]:
    ex = exclude.strip().lower()
    titles = []
    for d in plan.days:
        for p in d.places:
            t = p.title.strip()
            if t.lower() != ex:
                titles.append(t)
        if d.accommodation:
            t = d.accommodation.title.strip()
            if t.lower() != ex:
                titles.append(t)
    return titles

@router.post("/ai/repair-slot", response_model=DraftPlanCorrectedPlaceResponse)
async def repair_slot(req: DraftPlanCorrectionRequest):
    plan = req.draftPlanGeminiResponse
    correction = req.correctionPlace

    region_name = plan.label  # 초기 생성에서 label = region_name을 사용하셨으므로 그대로 사용
    label = plan.label.lower()
    is_acc = _is_accommodation_slot(plan, correction)
    slot_type = "accommodation" if is_acc else "place"
    place_type_csv = "B01" if is_acc else "A01,A02,A03"

    used_titles = _used_titles(plan, correction.title)

    client = await make_mcp_client()
    try:
        tools = await client.get_tools()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MCP bootstrap failed: {e}")

    llm = make_llm()
    agent = make_agent(llm, tools, system_prompt=SYSTEM_REPAIR)

    user_msg = build_repair_user_msg(
        region_name=region_name,
        label=label,
        slot_type=slot_type,
        place_type_csv=place_type_csv,
        problem_title=correction.title,
        problem_addr=correction.addr,
        problem_tel=correction.tel,
        used_titles=used_titles,
    )

    msgs = [HumanMessage(content=user_msg)]
    result = await agent.ainvoke({"messages": msgs})
    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
    tools_used = extract_tools_used(messages)

    # 툴 미사용 시 1회 강제 재시도
    if "get_places_page" not in tools_used:
        enforce = (
            "DO NOT answer yet.\n"
            "You must call get_places_page first with the given region_name and place_type_csv, page=0,size=40.\n"
            "Return ONLY the replacement JSON with fields {\"title\",\"addr\",\"tel\"}."
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

    try:
        data = json_from_agent(messages)
        fixed = DraftPlanCorrectedPlaceResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid replacement JSON: {e}")

    return fixed.model_dump()
