# 파일: /flows/EditTravelPlanFlow.py

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from travelPlan.PromptClassifyNodes import classify_user_intent
from travelPlan.nodes.SinglePlaceEditNodes import (
    run_single_edit_agent_node,
    verify_and_retry_node,
    generate_single_place_edit_response_node,
)
from travelPlan.EditState import EditState

# 기본 스테이트 설정
builder = StateGraph(EditState)

# 노드 등록
builder.add_node("classify_intent", classify_user_intent)
builder.add_node("run_single_edit_agent", run_single_edit_agent_node)
builder.add_node("verify_and_retry", verify_and_retry_node)
builder.add_node("generate_response", generate_single_place_edit_response_node)

# 시작점
builder.set_entry_point("classify_intent")

# intent에 따라 분기
builder.add_conditional_edges(
    "classify_intent",
    lambda state: state["intent"],
    {
        "single_edit": "run_single_edit_agent",
        # "partial_edit": "run_partial_edit_agent",  # 추후 확장
        # "full_edit": "run_full_edit_agent"
    }
)

# 단일 장소 편집 경로 정의
builder.add_edge("run_single_edit_agent", "verify_and_retry")
builder.add_edge("verify_and_retry", "generate_response")

# 종료 지점
builder.set_finish_point("generate_response")

# LangGraph 실행 준비
flow = builder.compile(checkpointer=MemorySaver())
