"""
Pydantic 请求/响应数据模型
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────────────────────────

class StartInterviewRequest(BaseModel):
    jd_text:         str            = Field(..., description="岗位 JD 文本")
    resume_text:     str            = Field("",  description="简历文本（可选）")
    user_id:         str            = Field("web_user", description="用户 ID")
    total_questions: int            = Field(5,   ge=1, le=20, description="出题数量")
    voice:           Optional[str]  = Field(None, description="TTS 音色")


class AnswerRequest(BaseModel):
    session_id:  str = Field(..., description="会话 ID")
    answer:      str = Field(..., description="用户回答文本")


class SkillRequest(BaseModel):
    session_id:  str = Field(..., description="会话 ID")
    skill_name:  str = Field(..., description="技能名称: quiz/teach/project/compare")
    user_input:  str = Field("",  description="技能输入内容")


# ── 响应模型 ──────────────────────────────────────────────────────────────────

class StartInterviewResponse(BaseModel):
    session_id:           str
    question:             str
    question_index:       int
    total_questions:      int
    difficulty:           str
    jd_title:             str = ""


class AnswerResponse(BaseModel):
    session_id:           str
    interview_finished:   bool
    should_followup:      bool
    question:             str            = ""   # 下一题或追问
    question_index:       int            = 0
    total_questions:      int            = 0
    difficulty:           str            = "medium"
    final_report:         Optional[Dict[str, Any]] = None
    study_plan:           Optional[Dict[str, Any]] = None
    github_recommendations: List[Dict[str, Any]]   = []


class ReportResponse(BaseModel):
    session_id:             str
    final_report:           Dict[str, Any]
    study_plan:             Dict[str, Any]
    github_recommendations: List[Dict[str, Any]] = []


class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str = "1.0.0"


class UploadResponse(BaseModel):
    filename:    str
    text:        str
    char_count:  int


class ErrorResponse(BaseModel):
    error:   str
    detail:  str = ""