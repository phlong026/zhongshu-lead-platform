from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class FollowUpBody(BaseModel):
    status: str = Field(pattern=r"^(UNCONTACTED|CONTACTED|INTERESTED|NOT_INTERESTED|DEAL|INVALID)$")
    note: str | None = Field(default=None, max_length=500)
    next_followup_at: datetime | None = None

    @model_validator(mode="after")
    def validate_effective(self):
        if self.status not in {"UNCONTACTED"} and not (self.note and self.note.strip()) and not self.next_followup_at:
            raise ValueError("有效跟进必须填写备注或下次跟进时间")
        return self
