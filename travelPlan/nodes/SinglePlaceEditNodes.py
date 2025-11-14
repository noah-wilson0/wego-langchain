# 파일: nodes/SinglePlaceEditNodes.py
import logging
from langchain_core.messages import HumanMessage
from TravelPlanModels import TravelPlanEditGeminiResponse
from travelPlan.prompts import SYSTEM_PROMPT_TEMPLATE, build_edit_user_msg
from utils import extract_tools_used, json_from_agent, last_text
from llm import make_llm, make_agent, make_mcp_client
from travelPlan.EditState import EditState  # ✨ 명확히 import
import json

logger = logging.getLogger(__name__)


# 기존 함수는 그대로 두고, 아래에 LangGraph용 노드 함수 래핑 추가 👇


# 1️⃣ run_single_edit_agent 노드
async def run_single_edit_agent_node(state: EditState) -> dict:
    request = state["request"]
    travel_plan = request["travelPlan"]
    prompt = state["user_prompt"]

    # MCP / LLM / Agent 구성
    client = await make_mcp_client()
    tools = await client.get_tools()
    agent = make_agent(make_llm(), tools, system_prompt=SYSTEM_PROMPT_TEMPLATE)

    day_times = [
        {"date": d["date"], "start_time": d["startTime"], "end_time": d["endTime"]}
        for d in travel_plan["days"]
    ]
    travel_plan_json_str = json.dumps(travel_plan, ensure_ascii=False, indent=2)

    user_msg = build_edit_user_msg(
        region_name=travel_plan["label"],
        start=travel_plan["startDate"],
        end=travel_plan["endDate"],
        day_times=day_times,
        travel_plan=travel_plan_json_str,
        user_requirements=prompt,
    )
    messages = [HumanMessage(content=user_msg)]
    logger.info("[Agent] USER_PROMPT:\n%s", user_msg)

    result = await agent.ainvoke({"messages": messages}, config={"recursion_limit": 80})
    return {**state, "messages": result["messages"]}


# 2️⃣ verify_and_retry 노드
async def verify_and_retry_node(state: EditState) -> dict:
    messages = state["messages"]
    request = state["request"]
    travel_plan = request["travelPlan"]

    # MCP / LLM / Agent 재구성
    client = await make_mcp_client()
    tools = await client.get_tools()
    agent = make_agent(make_llm(), tools, system_prompt=SYSTEM_PROMPT_TEMPLATE)

    tools_used = extract_tools_used(messages)
    raw_text = last_text(messages)
    logger.info("[Verify] Tools used: %s", tools_used)
    logger.info("[Verify] RAW OUTPUT:\n%s", raw_text)

    if "search_place_by_title" not in tools_used:
        enforce = (
            "STOP. You must call `search_place_by_title` tool for all ADD/REPLACE slots.\n"
            "Return only final TravelPlanEditGeminiResponse JSON."
        )
        messages.append(HumanMessage(content=enforce))
        result = await agent.ainvoke({"messages": messages}, config={"recursion_limit": 80})
        messages = result["messages"]

    return {**state, "messages": messages}


# 3️⃣ 최종 응답 생성 노드
async def generate_single_place_edit_response_node(state: EditState) -> dict:
    messages = state["messages"]
    raw_text = last_text(messages)

    try:
        plan_dict = json_from_agent(messages)
        response = TravelPlanEditGeminiResponse(**plan_dict)
        return {**state, "output": response.model_dump_json()}
    except Exception as e:
        logger.exception("[Final Parsing Failed] RAW=\n%s", raw_text)
        raise ValueError(f"Failed to parse TravelPlanEditGeminiResponse: {e}")
