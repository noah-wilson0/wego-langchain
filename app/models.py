from pydantic import BaseModel
from typing import Optional, List

class Place(BaseModel):
    place_id: int
    title: str
    place_type: str
    addr: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    average_rating: Optional[float] = None
    tel: Optional[str] = None

class PlacePage(BaseModel):
    items: List[Place]
    limit: int
    offset: int
    next_offset: Optional[int] = None
