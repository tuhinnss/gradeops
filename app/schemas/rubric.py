"""Rubric Pydantic schemas."""

from pydantic import BaseModel, Field


class PartialCreditRule(BaseModel):
    condition: str
    marks: float


class RubricItem(BaseModel):
    question_number: str
    max_marks: float
    key_points: list[str] = Field(default_factory=list)
    negative_conditions: list[str] = Field(default_factory=list)
    partial_credit_rules: list[PartialCreditRule] = Field(default_factory=list)


class RubricSchema(BaseModel):
    title: str = "Exam Rubric"
    items: list[RubricItem]

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "RubricSchema":
        if "items" in data:
            return cls.model_validate(data)
        if isinstance(data, list):
            return cls(items=[RubricItem.model_validate(i) for i in data])
        raise ValueError("Invalid rubric structure")
