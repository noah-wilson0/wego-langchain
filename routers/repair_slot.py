# #  v1
# from fastapi import APIRouter, HTTPException
# from langchain_core.messages import HumanMessage
# from models import (
#     DraftPlanCorrectionRequest,
#     DraftPlanCorrectedPlaceResponse,
#     DraftPlanGeminiResponse,
# )
# from prompts import SYSTEM_REPAIR, build_repair_user_msg
# from llm import make_mcp_client, make_llm, make_agent
# from utils import extract_tools_used, json_from_agent
#
# router = APIRouter()
#
# def _is_accommodation_slot(plan: DraftPlanGeminiResponse, correction: DraftPlanCorrectionRequest.CorrectionPlace) -> bool:
#     # accommodation과 title/addr/tel이 일치(느슨 비교)하면 숙소교체로 간주
#     target_title = correction.title.strip().lower()
#     for d in plan.days:
#         if d.accommodation:
#             if d.accommodation.title.strip().lower() == target_title:
#                 return True
#     return False
#
# def _used_titles(plan: DraftPlanGeminiResponse, exclude: str) -> list[str]:
#     ex = exclude.strip().lower()
#     titles = []
#     for d in plan.days:
#         for p in d.places:
#             t = p.title.strip()
#             if t.lower() != ex:
#                 titles.append(t)
#         if d.accommodation:
#             t = d.accommodation.title.strip()
#             if t.lower() != ex:
#                 titles.append(t)
#     return titles
#
# @router.post("/ai/repair-slot", response_model=DraftPlanCorrectedPlaceResponse)
# async def repair_slot(req: DraftPlanCorrectionRequest):
#     plan = req.draftPlanGeminiResponse
#     correction = req.correctionPlace
#
#     region_name = plan.label  # 초기 생성에서 label = region_name을 사용하셨으므로 그대로 사용
#     label = plan.label.lower()
#     is_acc = _is_accommodation_slot(plan, correction)
#     slot_type = "accommodation" if is_acc else "place"
#     place_type_csv = "B01" if is_acc else "A01,A02,A03"
#
#     used_titles = _used_titles(plan, correction.title)
#
#     client = await make_mcp_client()
#     try:
#         tools = await client.get_tools()
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"MCP bootstrap failed: {e}")
#
#     llm = make_llm()
#     agent = make_agent(llm, tools, system_prompt=SYSTEM_REPAIR)
#
#     user_msg = build_repair_user_msg(
#         region_name=region_name,
#         label=label,
#         slot_type=slot_type,
#         place_type_csv=place_type_csv,
#         problem_title=correction.title,
#         problem_addr=correction.addr,
#         problem_tel=correction.tel,
#         used_titles=used_titles,
#     )
#
#     msgs = [HumanMessage(content=user_msg)]
#     result = await agent.ainvoke({"messages": msgs})
#     messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
#     tools_used = extract_tools_used(messages)
#
#     # 툴 미사용 시 1회 강제 재시도
#     if "get_places_page" not in tools_used:
#         enforce = (
#             "DO NOT answer yet.\n"
#             "You must call get_places_page first with the given region_name and place_type_csv, page=0,size=40.\n"
#             "Return ONLY the replacement JSON with fields {\"title\",\"addr\",\"tel\"}."
#         )
#         msgs.append(HumanMessage(content=enforce))
#         result = await agent.ainvoke({"messages": msgs})
#         messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
#
#     try:
#         data = json_from_agent(messages)
#         fixed = DraftPlanCorrectedPlaceResponse(**data)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Invalid replacement JSON: {e}")
#
#     return fixed.model_dump()
#
#

#
# # v2 (logging 강화)
# import json
# import logging
# from fastapi import APIRouter, HTTPException
# from langchain_core.messages import HumanMessage
# from models import (
#     DraftPlanCorrectionRequest,
#     DraftPlanCorrectedPlaceResponse,
#     DraftPlanGeminiResponse,
# )
# from prompts import SYSTEM_REPAIR, build_repair_user_msg
# from llm import make_mcp_client, make_llm, make_agent
# from utils import extract_tools_used, json_from_agent
#
# logger = logging.getLogger(__name__)
# # 필요하면 앱 시작 시 한 번만 설정
# # logging.basicConfig(level=logging.INFO)
#
# router = APIRouter()
#
# def _json(obj) -> str:
#     try:
#         # pydantic 모델은 model_dump() 지원
#         if hasattr(obj, "model_dump"):
#             return json.dumps(obj.model_dump(), ensure_ascii=False, indent=2)
#         return json.dumps(obj, ensure_ascii=False, indent=2)
#     except Exception:
#         return str(obj)
#
# def _truncate(text: str, limit: int = 4000) -> str:
#     if text is None:
#         return ""
#     return text if len(text) <= limit else text[:limit] + "\n... [truncated]"
#
# def _is_accommodation_slot(plan: DraftPlanGeminiResponse, correction: DraftPlanCorrectionRequest.CorrectionPlace) -> bool:
#     target_title = (correction.title or "").strip().lower()
#     for d in plan.days:
#         if d.accommodation and (d.accommodation.title or "").strip().lower() == target_title:
#             return True
#     return False
#
# def _used_titles(plan: DraftPlanGeminiResponse, exclude: str) -> list[str]:
#     ex = (exclude or "").strip().lower()
#     titles = []
#     for d in plan.days:
#         for p in d.places:
#             t = (p.title or "").strip()
#             if t and t.lower() != ex:
#                 titles.append(t)
#         if d.accommodation:
#             t = (d.accommodation.title or "").strip()
#             if t and t.lower() != ex:
#                 titles.append(t)
#     return titles
#
# @router.post("/ai/repair-slot", response_model=DraftPlanCorrectedPlaceResponse)
# async def repair_slot(req: DraftPlanCorrectionRequest):
#     # 1) 요청 바디 로깅
#     logger.info("[repair-slot] incoming request:\n%s", _json(req))
#
#     plan = req.draftPlanGeminiResponse
#     correction = req.correctionPlace
#
#     region_name = plan.label  # 초기 생성에서 label == region_name 가정
#     label = (plan.label or "").lower()
#     is_acc = _is_accommodation_slot(plan, correction)
#     slot_type = "accommodation" if is_acc else "place"
#     place_type_csv = "B01" if is_acc else "A01,A02,A03"
#     used_titles = _used_titles(plan, correction.title)
#
#     logger.info(
#         "[repair-slot] context: region_name=%s, label=%s, slot_type=%s, place_type_csv=%s, used_titles=%d",
#         region_name, label, slot_type, place_type_csv, len(used_titles)
#     )
#
#     # 2) MCP 툴 목록 로깅
#     client = await make_mcp_client()
#     try:
#         tools = await client.get_tools()
#         tool_names = [getattr(t, "name", str(t)) for t in tools]
#         logger.info("[repair-slot] mcp tools: %s", tool_names)
#     except Exception as e:
#         logger.exception("[repair-slot] MCP bootstrap failed")
#         raise HTTPException(status_code=500, detail=f"MCP bootstrap failed: {e}")
#
#     llm = make_llm()
#     agent = make_agent(llm, tools, system_prompt=SYSTEM_REPAIR)
#
#     user_msg = build_repair_user_msg(
#         region_name=region_name,
#         label=label,
#         slot_type=slot_type,
#         place_type_csv=place_type_csv,
#         problem_title=correction.title,
#         problem_addr=correction.addr,
#         problem_tel=correction.tel,
#         used_titles=used_titles,
#     )
#     logger.debug("[repair-slot] user_msg prompt:\n%s", user_msg)
#
#     # 3) 1차 에이전트 호출 + 원문/툴 사용 로깅
#     msgs = [HumanMessage(content=user_msg)]
#     result = await agent.ainvoke({"messages": msgs})
#     messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
#
#     raw_chunks = []
#     for m in messages:
#         c = getattr(m, "content", None)
#         if c is not None:
#             raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
#     raw_text = "\n---\n".join(raw_chunks)
#     tools_used = extract_tools_used(messages)
#
#     logger.info("[repair-slot] tools_used after first call: %s", tools_used)
#     logger.info("[repair-slot] agent raw output (first):\n%s", _truncate(raw_text))
#
#     # 4) 툴 미사용 시 강제 재시도 + 원문/툴 사용 재로깅
#     if "get_places_page" not in tools_used:
#         enforce = (
#             "!! STOP. Return ONLY strict JSON, no explanations/no code fences.\n"
#             "You must call get_places_page first with the given region_name and place_type_csv, page=0,size=40.\n"
#             "Then answer with JSON object only: {\"title\":\"\",\"addr\":\"\",\"tel\":\"\"}"
#         )
#         msgs.append(HumanMessage(content=enforce))
#         result = await agent.ainvoke({"messages": msgs})
#         messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
#
#         raw_chunks = []
#         for m in messages:
#             c = getattr(m, "content", None)
#             if c is not None:
#                 raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
#         raw_text = "\n---\n".join(raw_chunks)
#         tools_used = extract_tools_used(messages)
#
#         logger.info("[repair-slot] tools_used after enforce: %s", tools_used)
#         logger.info("[repair-slot] agent raw output (enforced):\n%s", _truncate(raw_text))
#
#     # 5) JSON 파싱 시도 + 실패시 원문 동봉
#     try:
#         data = json_from_agent(messages)
#         logger.info("[repair-slot] parsed JSON from agent:\n%s", _json(data))
#         fixed = DraftPlanCorrectedPlaceResponse(**data)
#     except Exception as e:
#         logger.exception("[repair-slot] json_from_agent failed")
#         # detail에 요약을 담고, 전체 원문은 서버 로그로만 남김
#         summary = _truncate(raw_text, 1000)
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid replacement JSON: {e}. agent_output_preview={summary}"
#         )
#
#     return fixed  # response_model이 맞으므로 그대로 반환


# v2 (logging 강화 + 메시지 덤프)
import json
import logging
from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from models import (
    DraftPlanCorrectionRequest,
    DraftPlanCorrectedPlaceResponse,
    DraftPlanGeminiResponse,
)
from prompts import SYSTEM_REPAIR, build_repair_user_msg
    # make_mcp_client: MCP 클라이언트 생성
    # make_llm: LLM 인스턴스 생성
    # make_agent: tools + system_prompt로 Agent 구성
from llm import make_mcp_client, make_llm, make_agent
from utils import extract_tools_used, json_from_agent

logger = logging.getLogger(__name__)
# 필요하면 앱 시작 시 한 번만 설정 (uvicorn 옵션으로 대체 가능: --log-level info)
# logging.basicConfig(level=logging.INFO)

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
    """에이전트 메시지를 role/name/content + function_call/tool_calls까지 한 번에 덤프."""
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
        logger.info("[repair-slot] agent messages dump (%s)\n%s", tag, "\n".join(lines))
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
    # 1) 요청 바디 로깅
    logger.info("[repair-slot] incoming request:\n%s", _json(req))

    plan = req.draftPlanGeminiResponse
    correction = req.correctionPlace

    region_name = plan.label  # 초기 생성에서 label == region_name 가정
    label = (plan.label or "").lower()
    is_acc = _is_accommodation_slot(plan, correction)
    slot_type = "accommodation" if is_acc else "place"
    place_type_csv = "B01" if is_acc else "A01,A02,A03"
    used_titles = _used_titles(plan, correction.title)

    logger.info(
        "[repair-slot] context: region_name=%s, label=%s, slot_type=%s, place_type_csv=%s, used_titles=%d",
        region_name, label, slot_type, place_type_csv, len(used_titles)
    )

    # 2) MCP 툴 목록 로깅
    client = await make_mcp_client()
    try:
        tools = await client.get_tools()
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        logger.info("[repair-slot] mcp tools: %s", tool_names)
    except Exception as e:
        logger.exception("[repair-slot] MCP bootstrap failed")
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
    logger.debug("[repair-slot] user_msg prompt:\n%s", user_msg)

    # 3) 1차 에이전트 호출 + 원문/툴 사용 로깅
    msgs = [HumanMessage(content=user_msg)]
    result = await agent.ainvoke({"messages": msgs})
    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

    # 메시지 덤프
    _dump_messages(messages, tag="first")

    # 요약 텍스트/툴 사용/원문
    raw_chunks = []
    for m in messages:
        c = getattr(m, "content", None)
        if c is not None:
            raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    raw_text = "\n---\n".join(raw_chunks)
    tools_used = extract_tools_used(messages)

    logger.info("[repair-slot] tools_used after first call: %s", tools_used)
    logger.info("[repair-slot] agent raw output (first):\n%s", _truncate(raw_text))

    # 4) 툴 미사용 시 강제 재시도 + 원문/툴 사용 재로깅
    if "get_places_page" not in tools_used:
        enforce = (
            "!! STOP. Return ONLY strict JSON, no explanations/no code fences.\n"
            "You must call get_places_page first with the given region_name and place_type_csv, page=0,size=40.\n"
            "Then answer with JSON object only: {\"title\":\"\",\"addr\":\"\",\"tel\":\"\"}"
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

        # 메시지 덤프
        _dump_messages(messages, tag="enforced")

        raw_chunks = []
        for m in messages:
            c = getattr(m, "content", None)
            if c is not None:
                raw_chunks.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
        raw_text = "\n---\n".join(raw_chunks)
        tools_used = extract_tools_used(messages)

        logger.info("[repair-slot] tools_used after enforce: %s", tools_used)
        logger.info("[repair-slot] agent raw output (enforced):\n%s", _truncate(raw_text))

    # 5) JSON 파싱 시도 + 실패시 원문 동봉
    try:
        logger.info("[repair-slot] parsed JSON from agent:\n%s", messages)
        data = json_from_agent(messages)
        logger.info("[repair-slot] parsed JSON from agent:\n%s", _json(data))
        fixed = DraftPlanCorrectedPlaceResponse(**data)
    except Exception as e:
        logger.exception("[repair-slot] json_from_agent failed")
        logger.exception("[repair-slot] parsed JSON from agent:\n%s", messages)
        summary = _truncate(raw_text, 1000)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid replacement JSON: {e}. agent_output_preview={summary}"
        )

    return fixed  # response_model이 맞으므로 그대로 반환
