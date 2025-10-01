from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ====== 공용 스키마 ======
class Place(BaseModel):
    title: str
    addr: str
    tel: str

class Accommodation(BaseModel):
    title: str
    addr: str
    tel: str

class DayItem(BaseModel):
    date: str
    start_time: str
    end_time: str
    places: List[Place]
    accommodation: Optional[Accommodation] = None

class DraftPlanGeminiResponse(BaseModel):
    label: str
    start_date: str
    end_date: str
    days: List[DayItem]

# ====== /ai/generate-initial 요청 ======
class AutoGenerateInitialRequest(BaseModel):
    member_id: int
    region_name: str
    start_date: str
    end_date: str
    chemi: Dict[str, Any] = Field(default_factory=dict)

# ====== /ai/repair-slot 요청/응답 ======
class DraftPlanCorrectionRequest(BaseModel):
    draftPlanGeminiResponse: DraftPlanGeminiResponse
    class CorrectionPlace(BaseModel):
        title: str
        addr: str
        tel: str
    correctionPlace: CorrectionPlace

class DraftPlanCorrectedPlaceResponse(BaseModel):
    title: str
    addr: str
    tel: str
