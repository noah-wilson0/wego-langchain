from typing import List, Optional
from pydantic import BaseModel


# ===== 요청 DTO =====
class CompactPlace(BaseModel):
    title: str
    sequence: int


class CompactDay(BaseModel):
    date: str        # "YYYY-MM-DD"
    startTime: str   # "HH:mm"
    endTime: str     # "HH:mm"
    places: List[CompactPlace] = []  # title만


class CompactTravelPlan(BaseModel):
    label: str
    startDate: str   # LocalDate → ISO 문자열
    endDate: str     # LocalDate → ISO 문자열
    days: List[CompactDay] = []


class EditLanggraphRequest(BaseModel):
    prompt: str
    travelPlan: CompactTravelPlan


# ===== 응답 DTO =====
class PlacePatch(BaseModel):
    contentId: str
    title: str


class ChangeItem(BaseModel):
    date: str          # "YYYY-MM-DD"
    sequence: int      # 수정된 슬롯 번호
    beforePlace: Optional[PlacePatch] = None
    afterPlace: Optional[PlacePatch] = None


class TravelPlanEditGeminiResponse(BaseModel):
    changes: List[ChangeItem]




__all__ = [
    "EditLanggraphRequest",
    "CompactTravelPlan",
    "CompactDay",
    "CompactPlace",
    "TravelPlanEditGeminiResponse",
    "PlacePatch",
]
