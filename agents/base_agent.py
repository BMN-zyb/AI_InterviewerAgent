"""
Agent 基类：所有专职 Agent 的统一接口与公共能力
- 统一 run() 入口
- 统一 LLM 调用封装（基于 LangChain ChatTongyi）
- 统一日志 / 错误重试
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings


class BaseAgent(ABC):
    """所有 Agent 的抽象基类"""

    name: str = "base"
    description: str = ""

    def __init__(self) -> None:
        # 兼容 OpenAI 接口调用通义千问（通过 DashScope 兼容模式）
        self.llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.logger = logger.bind(agent=self.name)

    # ---------- 公共 LLM 调用（带重试） ----------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def invoke_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """调用 LLM 并返回文本，自动重试"""
        messages: List[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        llm = self.llm
        if temperature is not None:
            llm = self.llm.bind(temperature=temperature)
        if response_format:
            llm = llm.bind(response_format=response_format)  # type: ignore[attr-defined]
        resp = llm.invoke(messages)
        return resp.content or ""

    def invoke_llm_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """调用 LLM 并强制返回 JSON"""
        raw = self.invoke_llm(
            system_prompt + "\n\n请严格以合法 JSON 输出，不要任何多余文字。",
            user_prompt,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warning("LLM 返回非法 JSON，尝试提取：{}", raw[:200])
            # 兜底：尝试截取第一个 { ... }
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            raise

    def build_prompt(self, template: str, **kwargs: Any) -> str:
        return ChatPromptTemplate.from_template(template).format(**kwargs)

    # ---------- 统一入口 ----------
    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 节点签名：state -> state"""
        ...

    def __repr__(self) -> str:
        return f"<Agent name={self.name}>"
