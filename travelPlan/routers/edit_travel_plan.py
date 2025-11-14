# routers/edit_travel_plan.py

import logging
from fastapi import APIRouter, HTTPException
from google.api_core.operations_v1.operations_client_config import config

from travelPlan.flows.EditTravelPlanFlow import flow
from TravelPlanModels import (
    EditLanggraphRequest,
    TravelPlanEditGeminiResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ai/edit-travel-plan", response_model=TravelPlanEditGeminiResponse)
async def edit_travel_plan(req: EditLanggraphRequest):
    """
    LangGraph 기반의 여행 일정 '부분 수정' 처리 엔드포인트
    - 프롬프트를 기반으로 intent 분기 → single_edit 에이전트 → 검증 및 결과 생성까지 자동 처리
    """

    try:
        # LangGraph용 EditState 초기화
        state = {
            "user_prompt": req.prompt,
            "intent": "",
            "output": "",  # 최종 JSON 문자열이 여기 담김
            "request": req.model_dump(),  # 필요 시 각 노드에서 req 내용 사용 가능
        }

        logger.exception("[edit_travel_plan] LangGraph 시작 - user_prompt: %s", req.prompt)

        final_state = await flow.ainvoke(state, config={"configurable":{"thread_id": "test-run-001"}})

        # 출력 검증
        output = final_state.get("output", "")
        if not output:
            raise ValueError("output is empty")

        # JSON 파싱 후 반환
        return TravelPlanEditGeminiResponse.parse_raw(output)

    except Exception as e:
        logger.exception("LangGraph 기반 여행 편집 실패")
        raise HTTPException(status_code=500, detail=f"Edit flow failed: {e}")
