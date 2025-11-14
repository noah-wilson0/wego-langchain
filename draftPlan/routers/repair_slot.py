# nodes/repair_slot.py

import json
import logging
from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from draftPlan.prompts import SYSTEM_REPAIR, build_repair_user_msg
from draftPlan.DraftPlanModels import (
    DraftPlanCorrectionRequest,
    DraftPlanCorrectedPlaceResponse,
    DraftPlanGeminiResponse,
)
from llm import make_mcp_client, make_llm, make_agent
from utils import extract_tools_used, json_from_agent

logger = logging.getLogger(__name__)
router = APIRouter()

def _json(obj) -> str:
    try:
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(), ensure_ascii=False, indent=2)
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)

def _truncate(text: str, limit: int = 4000) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"

def _dump_messages(messages: list, tag: str = "first") -> None:
    try:
        lines = []
        for i, m in enumerate(messages):
            role = getattr(m, "type", getattr(m, "role", ""))
            name = getattr(m, "name", "")
            content = getattr(m, "content", "")
            ak = getattr(m, "additional_kwargs", {}) or {}
            tool_calls = ak.get("tool_calls", [])
            func_call = ak.get("function_call", {})
            content_preview = str(content)
            if content_preview and len(content_preview) > 1200:
                content_preview = content_preview[:1200] + "…"
            lines.append(
                f"#[{i}] role={role} name={name}\n"
                f"content={content_preview}\n"
                f"function_call={func_call}\n"
                f"tool_calls={tool_calls}\n"
            )
    except Exception:
        logger.exception("[repair-slot] message dump failed")

def _is_accommodation_slot(
    plan: DraftPlanGeminiResponse,
    correction: DraftPlanCorrectionRequest.CorrectionPlace
) -> bool:
    target_title = (correction.title or "").strip().lower()
    for d in plan.days:
        if d.accommodation and (d.accommodation.title or "").strip().lower() == target_title:
            return True
    return False

def _used_titles(plan: DraftPlanGeminiResponse, exclude: str) -> list[str]:
    ex = (exclude or "").strip().lower()
    titles = []
    for d in plan.days:
        for p in d.places:
            t = (p.title or "").strip()
            if t and t.lower() != ex:
                titles.append(t)
        if d.accommodation:
            t = (d.accommodation.title or "").strip()
            if t and t.lower() != ex:
                titles.append(t)
    return titles

@router.post("/ai/repair-slot", response_model=DraftPlanCorrectedPlaceResponse)
async def repair_slot(req: DraftPlanCorrectionRequest):
    """
    v2: 교체도 '먼저 구상 → MCP search_place_by_title로 정규화'를 강제.
    """
    # 1) 요청 로깅
    logger.info("[repair-slot] incoming request:\n%s", _json(req))

    plan = req.draftPlanGeminiResponse
    correction = req.correctionPlace

    region_name = plan.label  # 초기 생성에서 label == region_name 가정
    label = (plan.label or "").lower()
    is_acc = _is_accommodation_slot(plan, correction)
    slot_type = "accommodation" if is_acc else "place"
    place_type_csv = "B01" if is_acc else "A01,A02,A03"
    used_titles = _used_titles(plan, correction.title)

    # 2) MCP 툴
    client = await make_mcp_client()
    try:
        tools = await client.get_tools()
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        logger.info("[repair-slot] mcp tools: %s", tool_names)
    except Exception as e:
        logger.exception("[repair-slot] MCP bootstrap failed")
        raise HTTPException(status_code=500, detail="MCP bootstrap failed: " + str(e))

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

    # 3) 1차 실행
    msgs = [HumanMessage(content=user_msg)]
    result = await agent.ainvoke({"messages": msgs})
    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

    _dump_messages(messages, tag="first")
    raw_chunks = []
    for m in messages:
        c = getattr(m, "content", None)
        if c is not None:
            raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    raw_text = "\n---\n".join(raw_chunks)
    tools_used = extract_tools_used(messages)

    # 4) 툴 미사용 시 강제 재유도(정규화 보장)
    if "search_place_by_title" not in tools_used:
        json_skeleton = '{"title":"","addr":"","tel":""}'
        enforce = (
            "STOP. Normalize your ideated replacement using the DB via tool calls.\n"
            "For the chosen replacement, call: "
            "search_place_by_title(region_name='" + region_name + "', place_type='A01|A02|A03|B01', title='<title>').\n"
            "Return ONLY JSON: " + json_skeleton
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

        _dump_messages(messages, tag="enforced")
        raw_chunks = []
        for m in messages:
            c = getattr(m, "content", None)
            if c is not None:
                raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
        raw_text = "\n---\n".join(raw_chunks)
        tools_used = extract_tools_used(messages)

        logger.exception("[repair-slot] tools_used after enforce: %s", tools_used)
        logger.exception("[repair-slot] agent raw output (enforced):\n%s", _truncate(raw_text))

    # 5) JSON 파싱
    try:
        data = json_from_agent(messages)
        fixed = DraftPlanCorrectedPlaceResponse(**data)
    except Exception as e:
        logger.exception("[repair-slot] json_from_agent failed")
        summary = _truncate(raw_text, 1000)
        raise HTTPException(
            status_code=400,
            detail="Invalid replacement JSON: " + str(e) + ". agent_output_preview=" + summary
        )

    return fixed
