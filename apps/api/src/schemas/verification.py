from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerificationTemplateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=128)
    schema_definition: dict = Field(alias="schema")
    publish: bool = False


class VerificationTaskCreateBody(BaseModel):
    lead_ids: list[str] = Field(min_length=1, max_length=500)
    assignee_user_id: str | None = None
    template_code: str = "DEFAULT"


class VerificationAssignBody(BaseModel):
    assignee_user_id: str


class VerificationSubmitBody(BaseModel):
    result: str = Field(pattern=r"^(QUALIFIED|INVALID|NEED_MORE|DUPLICATE)$")
    invalid_reason: str | None = Field(default=None, max_length=64)
    answers: dict = Field(default_factory=dict)
    corrections: dict = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=1000)
