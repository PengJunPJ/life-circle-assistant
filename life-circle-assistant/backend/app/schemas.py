from typing import Literal

from pydantic import BaseModel, Field, field_validator


CoreCategory = Literal["market", "pharmacy", "school", "medical"]

class AnalyzeRequest(BaseModel):
    lng: float = Field(default=113.4872, ge=-180, le=180)
    lat: float = Field(default=23.1068, ge=-90, le=90)
    minutes: Literal[10, 15, 20] = 15
    mode: Literal["demo", "analysis"] = "demo"
    categories: list[CoreCategory] = Field(default_factory=lambda: ["market", "pharmacy", "school", "medical"], min_length=1)

    @field_validator("categories")
    @classmethod
    def deduplicate_categories(cls, categories: list[CoreCategory]) -> list[CoreCategory]:
        return list(dict.fromkeys(categories))
