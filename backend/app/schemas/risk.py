"""Risk schemas (Steps 11–12).

Field names mirror ``frontend/src/api/types.ts`` exactly — the Findings and
RiskTraining pages already speak this contract.
"""

from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]


class RiskFindingRead(BaseModel):
    id: UUID
    repo_id: UUID
    symbol_id: UUID
    risk_level: str
    probability: float
    features_json: Dict = Field(default_factory=dict)
    model_version: str
    created_at: object
    updated_at: object
    # Display context, joined from symbols/files: a table of UUIDs is
    # useless, and the Findings page renders these columns.
    symbol_name: str = ""
    symbol_kind: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0

    model_config = {"from_attributes": True}


class RiskFindingListResponse(BaseModel):
    repo_id: UUID
    findings: List[RiskFindingRead]
    total: int
    limit: int
    offset: int


class FindingsSummary(BaseModel):
    repo_id: UUID
    by_level: Dict[str, int]
    total: int


class TrainRequest(BaseModel):
    repo_ids: Optional[List[UUID]] = None
    model_type: str = "logistic"


class TrainResponse(BaseModel):
    ok: bool
    message: str


class EvaluateResponse(BaseModel):
    ok: bool
    message: str
