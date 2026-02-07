"""
NetAIOps Chat Frontend - Message Model
NetAIOps 채팅 프론트엔드 - 메시지 모델

This module defines the Message model for chat conversations.
이 모듈은 채팅 대화를 위한 메시지 모델을 정의합니다.
"""

from datetime import datetime
from typing import Dict

from pydantic import BaseModel


class Message(BaseModel):
    """
    Message model for chat conversations.
    채팅 대화를 위한 메시지 모델.

    Attributes:
        role: Message role ("user" or "assistant") / 메시지 역할 ("user" 또는 "assistant")
        content: Message content / 메시지 내용
        timestamp: Message timestamp / 메시지 타임스탬프
        metadata: Additional metadata / 추가 메타데이터
    """

    role: str
    content: str
    timestamp: datetime
    metadata: Dict = {}

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
