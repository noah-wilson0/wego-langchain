# travelPlan/EditState.py
from typing import Any

from typing_extensions import TypedDict

class EditState(TypedDict):
    user_prompt: str
    intent: str
    output: str
    request: dict
    messages: list[Any]