from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from models import AutoGenerateInitialRequest, DraftPlanGeminiResponse
from prompts import SYSTEM_INITIAL, build_initial_user_msg
from llm import make_mcp_client, make_llm, make_agent
from utils import extract_tools_used, json_from_agent

router = APIRouter()

@router.post("/ai/generate-initial", response_model=DraftPlanGeminiResponse)
async def generate_initial(req: AutoGenerateInitialRequest):
    client = await make_mcp_client()
    try:
        tools = await client.get_tools()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MCP bootstrap failed: {e}")

    llm = make_llm()
    agent = make_agent(llm, tools, system_prompt=SYSTEM_INITIAL)

    user_msg = build_initial_user_msg(
        region_name=req.region_name, start=req.start_date, end=req.end_date
    )
    msgs = [HumanMessage(content=user_msg)]
    result = await agent.ainvoke({"messages": msgs})

    messages = result["messages"] if isinstance(result, dict) and "messages" in result else []
    tools_used = extract_tools_used(messages)

    # 툴 미사용 시 1회 강제 재시도
    if "get_places_page" not in tools_used:
        place_types = "A01,A02,A03,B01"
        enforce = (
            "DO NOT answer yet.\n"
            "First, call get_places_page NOW with exactly:\n"
            f'{{"region_name":"{req.region_name}","place_type_csv":"{place_types}","page":0,"size":20}}\n'
            "Return the Observation and then the final DraftPlanGeminiResponse JSON."
        )
        msgs.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": msgs})
        messages = result["messages"] if isinstance(result, dict) and "messages" in result else []

    try:
        plan_dict = json_from_agent(messages)
        plan = DraftPlanGeminiResponse(**plan_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid plan JSON: {e}")

    return plan.model_dump()
