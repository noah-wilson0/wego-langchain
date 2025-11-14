
from travelPlan.EditState import EditState


# ===== 프롬프트 분류 노드 =====
def classify_user_intent(state: EditState) -> dict:
    prompt = state["user_prompt"]

    # 조건 분기 키워드 기반
    if any(kw in prompt for kw in ["전체", "전반", "다시", "스타일", "새로", "처음부터"]):
        return {"intent": "full_edit"}

    elif any(kw in prompt for kw in ["이 일정만", "이 장소만", "이것만", "여기만", "한 곳만", "한군데만", "하나만", "일차"]):
        return {"intent": "single_edit"}

    else:
        return {"intent": "partial_edit"}






