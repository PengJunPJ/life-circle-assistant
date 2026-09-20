from typing import Literal
from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    lng: float = Field(default=113.4872)
    lat: float = Field(default=23.1068)
    minutes: Literal[10, 15, 20] = 15
    mode: Literal["demo", "analysis"] = "demo"
    categories: list[str] = ["market", "pharmacy", "school", "medical"]

