"""
WebSocket 路由：/ws/{session_id}
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from audio.stt import stt_engine
from audio.tts import tts_engine
from memory.memory_manager import memory_manager

router = APIRouter(tags=["WebSocket"])


def _get_graph():
    from orchestration.graph import get_compiled_graph
    return get_compiled_graph()


async def _send_json(ws: WebSocket, data: Dict[str, Any]) -> bool:
    """安全发送 JSON，返回是否成功"""
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning("WebSocket 发送失败: {}", e)
        return False


async def _send_tts(ws: WebSocket, text: str, voice: Optional[str] = None) -> None:
    """TTS 合成并推流"""
    if not text.strip() or not tts_engine.available:
        return
    await _send_json(ws, {"type": "tts_start"})
    try:
        async for chunk in tts_engine.synthesize_stream(text, voice=voice):
            await ws.send_bytes(chunk)
    except Exception as e:
        logger.error("TTS 推流异常: {}", e)
    finally:
        await _send_json(ws, {"type": "tts_end"})


def _build_short_term_snapshot(state: Dict) -> Dict:
    """
    ★ 从 state 中提取短期记忆快照，透传给前端记忆面板
    包含：qa_history、当前题目索引、难度、score_records
    """
    qa_history = state.get("qa_history", [])
    return {
        "qa_history":            qa_history,
        "current_question_idx":  state.get("current_question_idx", 0),
        "current_difficulty":    state.get("current_difficulty", "medium"),
        "score_records":         state.get("score_records", []),
        "total_questions":       state.get("total_questions", 0),
        "long_term_weaknesses":  state.get("long_term_weaknesses", []),
    }


async def _handle_start(
    ws: WebSocket,
    data: Dict[str, Any],
    session_id: str,
    graph,
) -> Optional[Dict]:
    jd_text         = data.get("jd_text", "").strip()
    resume_text     = data.get("resume_text", "").strip()
    total_questions = int(data.get("total_questions", 5))
    user_id         = data.get("user_id", "web_user")
    voice           = data.get("voice")

    if not jd_text:
        await _send_json(ws, {"type": "error", "message": "JD 内容不能为空"})
        return None

    init_state = {
        "session_id":           session_id,
        "user_id":              user_id,
        "jd_text":              jd_text,
        "resume_text":          resume_text,
        "intent":               "start_interview",
        "user_input":           "开始面试",
        "current_difficulty":   "medium",
        "current_question_idx": 0,
        "qa_history":           [],
        "score_records":        [],
        "awaiting_answer":      False,
        "awaiting_evaluation":  False,
        "interview_finished":   False,
        "should_followup":      False,
        "followup_count":       0,
        "max_followup":         2,
        "force_finish":         False,
        "skill_state":          {},
        "total_questions":      total_questions,
        "_voice":               voice,
    }

    try:
        state = graph.invoke(init_state)
    except Exception as e:
        logger.error("面试启动失败: {}", e)
        await _send_json(ws, {"type": "error", "message": f"面试启动失败: {e}"})
        return None

    memory_manager.save_session(session_id, state)

    question = state.get("current_question_text", "")
    if not question:
        await _send_json(ws, {"type": "error", "message": "题目生成失败"})
        return None

    plan = state.get("question_plan", [])
    await _send_json(ws, {
        "type":           "question",
        "text":           question,
        "index":          state.get("current_question_idx", 0) + 1,
        "total":          len(plan),
        "difficulty":     state.get("current_difficulty", "medium"),
        "jd_title":       state.get("jd_parsed", {}).get("title", ""),
        # ★ 透传短期记忆快照
        "memory_snapshot": _build_short_term_snapshot(state),
    })
    await _send_tts(ws, question, voice=voice)
    return state


async def _handle_answer(
    ws: WebSocket,
    answer_text: str,
    state: Dict,
    graph,
) -> Dict:
    session_id = state.get("session_id", "")
    voice      = state.get("_voice")

    state["user_input"]          = answer_text
    state["last_user_answer"]    = answer_text
    state["intent"]              = "answer_question"
    state["awaiting_evaluation"] = True
    state["awaiting_answer"]     = False

    try:
        state = graph.invoke(state)
    except Exception as e:
        logger.error("回答处理失败: {}", e)
        await _send_json(ws, {"type": "error", "message": f"处理失败: {e}"})
        return state

    memory_manager.save_session(session_id, state)

    # ── 面试结束 ──────────────────────────────────────────────────────────
    if state.get("interview_finished", False):
        farewell = state.get("agent_reply", "感谢参与本次模拟面试！")
        await _send_json(ws, {
            "type":                   "finished",
            "farewell":               farewell,
            "report":                 state.get("final_report", {}),
            "study_plan":             state.get("study_plan", {}),
            "github_recommendations": state.get("github_recommendations", []),
            # ★ 透传完整记忆快照（含 qa_history）
            "memory_snapshot":        _build_short_term_snapshot(state),
            "long_term_weaknesses":   state.get("long_term_weaknesses", []),
        })
        if farewell:
            await _send_tts(ws, farewell, voice=voice)
        return state

    # ── 追问 ──────────────────────────────────────────────────────────────
    if state.get("should_followup", False):
        followup_q = state.get("current_question_text", "")
        await _send_json(ws, {
            "type":            "followup",
            "text":            followup_q,
            # ★ 透传记忆快照
            "memory_snapshot": _build_short_term_snapshot(state),
        })
        await _send_tts(ws, followup_q, voice=voice)
        return state

    # ── 下一题 ────────────────────────────────────────────────────────────
    next_q = state.get("current_question_text", "")
    plan   = state.get("question_plan", [])
    await _send_json(ws, {
        "type":            "question",
        "text":            next_q,
        "index":           state.get("current_question_idx", 0) + 1,
        "total":           len(plan),
        "difficulty":      state.get("current_difficulty", "medium"),
        # ★ 透传记忆快照
        "memory_snapshot": _build_short_term_snapshot(state),
    })
    await _send_tts(ws, next_q, voice=voice)
    return state


async def _handle_skill(
    ws: WebSocket,
    data: Dict[str, Any],
    state: Dict,
    graph,
) -> Dict:
    session_id = state.get("session_id", "")
    skill_name = data.get("skill_name", "quiz")
    user_input = data.get("user_input", "")
    voice      = state.get("_voice")

    skill_state             = dict(state)
    skill_state["intent"]     = "use_skill"
    skill_state["skill_name"] = skill_name
    skill_state["user_input"] = user_input

    try:
        result = graph.invoke(skill_state)
    except Exception as e:
        await _send_json(ws, {"type": "error", "message": f"技能调用失败: {e}"})
        return state

    reply = result.get("agent_reply", "")
    await _send_json(ws, {
        "type":       "skill_reply",
        "skill_name": skill_name,
        "text":       reply,
    })
    await _send_tts(ws, reply, voice=voice)

    state["skill_state"] = result.get("skill_state", {})
    memory_manager.save_session(session_id, state)
    return state


# ── WebSocket 主处理器 ────────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    await ws.accept()

    if session_id == "new":
        session_id = str(uuid.uuid4())
        await _send_json(ws, {"type": "session_id", "session_id": session_id})

    logger.info("WebSocket 连接建立: {}", session_id)

    graph       = _get_graph()
    state: Dict = memory_manager.load_session(session_id) or {}
    _connected  = True   # ★ 本地连接标志，避免断开后继续操作

    try:
        while True:
            message = await ws.receive()

            # ── 连接已关闭 ────────────────────────────────────────────────
            if message.get("type") == "websocket.disconnect":
                logger.info("WebSocket 客户端主动断开: {}", session_id)
                _connected = False
                break

            # ── 二进制音频帧 ──────────────────────────────────────────────
            if "bytes" in message and message["bytes"]:
                audio_bytes = message["bytes"]
                logger.debug("收到音频帧: {} bytes", len(audio_bytes))

                # ★ STT 识别，仅回传文字到输入框，不自动发送回答
                text = stt_engine.transcribe_bytes(audio_bytes, is_wav=False)
                await _send_json(ws, {
                    "type":    "stt_result",
                    "text":    text,
                    "message": "" if text else "未识别到语音，请重试",
                })
                continue

            # ── 文本 JSON 消息 ────────────────────────────────────────────
            if "text" not in message or not message["text"]:
                continue

            try:
                data = json.loads(message["text"])
            except json.JSONDecodeError:
                await _send_json(ws, {"type": "error", "message": "JSON 格式错误"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await _send_json(ws, {"type": "pong"})

            elif msg_type == "start":
                state = await _handle_start(ws, data, session_id, graph) or {}

            elif msg_type == "answer":
                if not state:
                    await _send_json(ws, {"type": "error", "message": "请先发送 start 消息"})
                    continue
                answer_text = data.get("text", "").strip()
                if not answer_text:
                    await _send_json(ws, {"type": "error", "message": "回答不能为空"})
                    continue
                state = await _handle_answer(ws, answer_text, state, graph)

            elif msg_type == "skill":
                if not state:
                    await _send_json(ws, {"type": "error", "message": "请先发送 start 消息"})
                    continue
                state = await _handle_skill(ws, data, state, graph)

            else:
                await _send_json(ws, {"type": "error", "message": f"未知消息类型: {msg_type}"})

    except WebSocketDisconnect:
        _connected = False
        logger.info("WebSocket 断开: {}", session_id)
    except Exception as e:
        _connected = False
        logger.error("WebSocket 异常: {} {}", session_id, e)
        # ★ 只在连接仍有效时才尝试发送错误
        if _connected:
            try:
                await _send_json(ws, {"type": "error", "message": str(e)})
            except Exception:
                pass
    finally:
        if state:
            memory_manager.save_session(session_id, state)
        logger.info("WebSocket 连接关闭: {}", session_id)