"""
短期记忆（Redis）：当前会话上下文
- 会话窗口（最近 N 轮对话）
- 当前面试状态快照
- 24 小时 TTL 自动过期
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from config import settings


def _safe_serialize(obj: Any) -> Any:
    """
    JSON 序列化辅助：递归处理不可序列化的对象。
    - BaseMessage 等 LangChain 对象 → 转为 dict
    - 其余不可序列化对象 → 转为 str
    """
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_serialize(v) for v in obj]
    # LangChain BaseMessage
    try:
        from langchain_core.messages import BaseMessage
        if isinstance(obj, BaseMessage):
            return {"__lc_msg__": True, "type": obj.type, "content": obj.content}
    except ImportError:
        pass
    # 其他不可 JSON 序列化的类型
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


class ShortTermMemory:
    """基于 Redis 的短期记忆（带容错）"""

    def __init__(self) -> None:
        self._client    = None
        self._available = None   # None=未检测
        self.ttl        = settings.redis_short_term_ttl

    def _ensure_connected(self) -> bool:
        """惰性连接"""
        if self._available is True:
            return True
        if self._available is False:
            return False
        try:
            import redis
            client = redis.Redis(
                host     = settings.redis_host,
                port     = settings.redis_port,
                password = settings.redis_password or None,
                db       = settings.redis_db,
                decode_responses = True,
                socket_connect_timeout = 3,
            )
            client.ping()
            self._client    = client
            self._available = True
            logger.info("Redis 短期记忆已连接")
            return True
        except Exception as e:
            self._available = False
            logger.warning("Redis 不可用，短期记忆降级为内存：{}", e)
            self._mem_store: Dict[str, Any] = {}   # 内存降级
            return False

    def _key(self, session_id: str, kind: str) -> str:
        return f"iam:short:{session_id}:{kind}"

    # ── 对话窗口 ──────────────────────────────────────────────────────────────

    def append_turn(
        self, session_id: str, role: str, content: str, max_turns: int = 20
    ) -> None:
        turn = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        if not self._ensure_connected():
            return   # 降级时忽略
        try:
            key = self._key(session_id, "turns")
            self._client.rpush(key, turn)
            self._client.ltrim(key, -max_turns, -1)
            self._client.expire(key, self.ttl)
        except Exception as e:
            logger.warning("append_turn 失败：{}", e)

    def get_turns(self, session_id: str) -> List[Dict[str, str]]:
        if not self._ensure_connected():
            return []
        try:
            key = self._key(session_id, "turns")
            raw = self._client.lrange(key, 0, -1) or []
            return [json.loads(r) for r in raw]
        except Exception as e:
            logger.warning("get_turns 失败：{}", e)
            return []

    # ── 状态快照 ──────────────────────────────────────────────────────────────

    def save_state_snapshot(self, session_id: str, snapshot: Dict[str, Any]) -> None:
        if not self._ensure_connected():
            # 降级到内存
            if hasattr(self, "_mem_store"):
                self._mem_store[session_id] = snapshot
            return
        try:
            key        = self._key(session_id, "snapshot")
            # ★ 用 _safe_serialize 处理 BaseMessage 等不可序列化对象
            safe_snap  = _safe_serialize(snapshot)
            serialized = json.dumps(safe_snap, ensure_ascii=False)
            self._client.set(key, serialized, ex=self.ttl)
        except Exception as e:
            logger.warning("save_state_snapshot 失败：{}", e)

    def get_state_snapshot(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self._ensure_connected():
            if hasattr(self, "_mem_store"):
                return self._mem_store.get(session_id)
            return None
        try:
            key = self._key(session_id, "snapshot")
            raw = self._client.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("get_state_snapshot 失败：{}", e)
            return None

    def clear(self, session_id: str) -> None:
        if not self._ensure_connected():
            if hasattr(self, "_mem_store"):
                self._mem_store.pop(session_id, None)
            return
        try:
            pattern = self._key(session_id, "*")
            keys    = self._client.keys(pattern)
            if keys:
                self._client.delete(*keys)
                logger.info("清除短期记忆：{} 个 key", len(keys))
        except Exception as e:
            logger.warning("clear 失败：{}", e)