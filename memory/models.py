"""SQLAlchemy ORM 模型定义（长期记忆）"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    """用户画像（长期记忆核心）"""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_interviews = Column(Integer, default=0)
    average_score = Column(Integer, default=0)
    persistent_weaknesses = Column(JSON, default=list)  # 持久化薄弱点
    tech_strengths = Column(JSON, default=list)          # 技术优势


class InterviewRecord(Base):
    """面试历史记录"""
    __tablename__ = "interview_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=False)
    session_id = Column(String(64), unique=True, nullable=False)
    interview_date = Column(DateTime, default=datetime.utcnow)
    jd_title = Column(String(200))
    overall_score = Column(Integer)
    recommendation = Column(String(32))
    report_json = Column(JSON)
    study_plan_json = Column(JSON)
    weaknesses = Column(JSON, default=list)


class KnowledgeNote(Base):
    """知识点笔记（用户标注/收藏的面试知识点）"""
    __tablename__ = "knowledge_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), index=True, nullable=False)
    topic = Column(String(200), nullable=False)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
