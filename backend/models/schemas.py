from pydantic import BaseModel, Field
from typing import List

class PolicyChunkResponse(BaseModel):
    message: str
    chunks_inserted: int

class AuditResult(BaseModel):
    id: str
    question_text: str
    status: str
    evidence: str

class AuditProcessResponse(BaseModel):
    message: str
    results: List[AuditResult]

class QuestionEvaluation(BaseModel):
    status: str = Field(description="Must be 'Met' or 'Not Met'")
    evidence: str = Field(description="Extract the precise evidence or reason for the status from the policy document.")
