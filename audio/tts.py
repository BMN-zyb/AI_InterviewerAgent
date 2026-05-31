"""
TTS 语音合成：通义千问 CosyVoice API
- 流式合成（AsyncIterator[bytes]）供 WebSocket 实时推送
- 同步合成（bytes）供 REST API 返回
- 自动降级：API 不可用时返回空字节，不中断主流程
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Optional

import httpx
from loguru import logger

from config.settings import settings

# CosyVoice REST API 端点
_COSYVOICE_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2audio/text-synthesis"
)

# 支持的音色列表（供前端选择）
AVAILABLE_VOICES = [
    "longxiaochun",   # 龙小淳（女，温柔）
    "longxiaoxia",    # 龙小夏（女，活泼）
    "longjiangwai",   # 龙江外（男，沉稳）
    "longyue",        # 龙悦（女，专业）
]


class TTSEngine:
    """
    TTS 引擎（CosyVoice 流式 + 同步双模式）
    
    Args:
        voice:       音色名称
        audio_format: 输出格式，mp3 / wav / pcm
        sample_rate:  采样率
    """

    def __init__(
        self,
        voice: str        = "longxiaochun",
        audio_format: str = "mp3",
        sample_rate: int  = 22050,
    ) -> None:
        self.voice        = voice
        self.audio_format = audio_format
        self.sample_rate  = sample_rate
        self._api_key     = getattr(settings, "dashscope_api_key", "") or ""

        if not self._api_key:
            logger.warning("DASHSCOPE_API_KEY 未配置，TTS 功能不可用")

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    # ── 流式合成（WebSocket 推流） ─────────────────────────────────────────────

    async def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """
        流式合成音频，逐块 yield bytes
        
        Usage:
            async for chunk in tts_engine.synthesize_stream(text):
                await websocket.send_bytes(chunk)
        """
        if not self.available:
            logger.warning("TTS 不可用，跳过合成")
            return

        if not text.strip():
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type":  "application/json",
            "X-DashScope-SSE": "enable",
        }
        payload = {
            "model": "cosyvoice-v1",
            "input": {"text": text},
            "parameters": {
                "voice":       voice or self.voice,
                "format":      self.audio_format,
                "sample_rate": self.sample_rate,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST", _COSYVOICE_URL,
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        logger.error(
                            "TTS API 错误: {} {}", resp.status_code, body[:200]
                        )
                        return

                    async for chunk in resp.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk

        except httpx.TimeoutException:
            logger.error("TTS 请求超时")
        except Exception as e:
            logger.error("TTS 流式合成异常: {}", e)

    # ── 同步合成（REST API 返回） ──────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> bytes:
        """
        同步合成，返回完整音频字节
        
        适合 REST 接口：response = tts_engine.synthesize(text)
        """
        if not self.available or not text.strip():
            return b""

        chunks: list[bytes] = []

        async def _collect() -> None:
            async for chunk in self.synthesize_stream(text, voice=voice):
                chunks.append(chunk)

        try:
            # 兼容已有事件循环（FastAPI 环境）和无事件循环（脚本环境）
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在 FastAPI 中，使用 asyncio.run_coroutine_threadsafe
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(_collect(), loop)
                    future.result(timeout=60)
                else:
                    loop.run_until_complete(_collect())
            except RuntimeError:
                asyncio.run(_collect())
        except Exception as e:
            logger.error("TTS 同步合成失败: {}", e)
            return b""

        return b"".join(chunks)

    async def synthesize_async(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> bytes:
        """异步全量合成（FastAPI async 路由使用）"""
        chunks: list[bytes] = []
        async for chunk in self.synthesize_stream(text, voice=voice):
            chunks.append(chunk)
        return b"".join(chunks)


# 全局单例
tts_engine = TTSEngine()