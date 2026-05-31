"""
WebSocket 路由：/ws/{session_id}

消息协议：
  客户端->服务端:
    {"type":"start", "jd_text":"...", "resume_text":"...",
     "total_questions":5, "voice":"longxiaochun", "user_id":"web_user"}
    {"type":"answer",  "text":"用户回答"}
    {"type":"force_finish"}           - 强制结束面试生成报告
    {"type":"get_memory"}             - 主动拉取记忆数据
    {"type":"clear_long_memory"}      - 清除长期记忆薄弱点
    {"type":"get_rag"}                - 查看RAG检索结果
    {"type":"tts_speak", "text":"...", "voice":"..."} - 朗读指定文本
    {"type":"skill", "skill_name":"...", "user_input":"..."}
    {"type":"ping"}

  服务端->客户端:
    {"type":"question",  "text":"...", "index":1, "total":5,
                         "difficulty":"medium", "memory_snapshot":{...}}
    {"type":"followup",  "text":"...", "memory_snapshot":{...}}
    {"type":"finished",  "farewell":"...", "report":{},
                         "study_plan":{}, "github_recommendations":[],
                         "memory_snapshot":{...}}
    {"type":"skill_reply", "skill_name":"...", "text":"..."}
    {"type":"stt_result",  "text":"...", "message":""}
    {"type":"memory_data", "short_term":{...}, "long_term":{...}}
    {"type":"rag_data",    "rag_sources":[...], "rag_context":"...", "total":N}
    {"type":"toast",       "msg":"...", "level":"success|warning|error|info"}
    {"type":"tts_start"}  {"type":"tts_end"}
    {"type":"error",       "message":"..."}
    {"type":"pong"}

  服务端->客户端(二进制): TTS 音频数据块
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from audio.stt import stt_engine
from audio.tts import tts_engine
from memory.memory_manager import memory_manager

router = APIRouter(tags=["WebSocket"])


def _get_graph():
    from orchestration.graph import get_compiled_graph
    return get_compiled_graph()


# ── 基础发送 ──────────────────────────────────────────────────────────────────

async def _send_json(ws: WebSocket, data: Dict[str, Any]) -> bool:
    """安全发送 JSON"""
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning("WebSocket 发送失败: {}", e)
        return False


async def _send_tts(ws: WebSocket, text: str, voice: Optional[str] = None) -> None:
    """
    TTS 合成推流。
    无论是否有音频数据，都发 tts_start / tts_end，
    确保前端 TtsPlayer 指示器正确关闭。
    """
    await _send_json(ws, {"type": "tts_start"})

    if not text or not text.strip():
        await _send_json(ws, {"type": "tts_end"})
        return

    if not tts_engine.available:
        logger.debug("TTS 不可用（DASHSCOPE_API_KEY 未配置），跳过合成")
        await _send_json(ws, {"type": "tts_end"})
        return

    try:
        chunk_count = 0
        async for chunk in tts_engine.synthesize_stream(text, voice=voice):
            await ws.send_bytes(chunk)
            chunk_count += 1
        logger.debug("TTS 推流完成: {} 块, voice={}", chunk_count, voice)
    except Exception as e:
        logger.error("TTS 推流异常: {}", e)
    finally:
        await _send_json(ws, {"type": "tts_end"})


# ── State 辅助 ────────────────────────────────────────────────────────────────

def _safe_extract_qa_history(state: Dict) -> List[Dict]:
    """
    安全提取 qa_history，确保每条记录完全可 JSON 序列化。
    qa_history 格式: [{"question": str, "answer": str, "score": dict}]
    """
    raw = state.get("qa_history", [])
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        score = item.get("score", {})
        if not isinstance(score, dict):
            score = {}
        result.append({
            "question": str(item.get("question", "")),
            "answer":   str(item.get("answer", "")),
            "score": {
                "correctness":     int(score.get("correctness", 0)),
                "depth":           int(score.get("depth", 0)),
                "structure":       int(score.get("structure", 0)),
                "example":         int(score.get("example", 0)),
                "is_correct":      bool(score.get("is_correct", False)),
                "followup_needed": bool(score.get("followup_needed", False)),
                "key_missing":     [str(k) for k in score.get("key_missing", [])],
            },
        })
    return result


def _build_short_term_snapshot(state: Dict) -> Dict:
    """构建短期记忆快照，随每条 WS 消息透传给前端"""
    return {
        "qa_history":           _safe_extract_qa_history(state),
        "current_question_idx": int(state.get("current_question_idx", 0)),
        "current_difficulty":   str(state.get("current_difficulty", "medium")),
        "score_records_count":  len(state.get("score_records", [])),
        "total_questions":      int(state.get("total_questions", 0)),
        "long_term_weaknesses": list(state.get("long_term_weaknesses", [])),
    }


async def _get_fresh_long_term(user_id: str, fallback: list) -> list:
    """从 MySQL 获取最新长期记忆，失败时用 fallback"""
    try:
        result = memory_manager.get_weaknesses(user_id)
        return result if result is not None else fallback
    except Exception:
        return fallback


async def _send_memory_data(ws: WebSocket, state: Dict, user_id: str) -> None:
    """主动推送完整记忆数据给前端"""
    fresh_weaknesses = await _get_fresh_long_term(
        user_id, list(state.get("long_term_weaknesses", []))
    )
    snapshot = _build_short_term_snapshot(state)
    snapshot["long_term_weaknesses"] = fresh_weaknesses
    await _send_json(ws, {
        "type":       "memory_data",
        "short_term": snapshot,
        "long_term":  {"weaknesses": fresh_weaknesses},
    })


# ── 业务处理函数 ──────────────────────────────────────────────────────────────

async def _handle_start(
    ws: WebSocket,
    data: Dict[str, Any],
    session_id: str,
    graph,
) -> Optional[Dict]:
    """处理 start 消息，初始化面试"""
    jd_text         = data.get("jd_text", "").strip()
    resume_text     = data.get("resume_text", "").strip()
    total_questions = int(data.get("total_questions", 5))
    user_id         = data.get("user_id", "web_user")
    voice           = data.get("voice")

    if not jd_text:
        await _send_json(ws, {"type": "error", "message": "JD 内容不能为空"})
        return None

    # 加载历史长期记忆
    long_term_weaknesses = await _get_fresh_long_term(user_id, [])

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
        "long_term_weaknesses": long_term_weaknesses,
    }

    try:
        state = graph.invoke(init_state)
    except Exception as e:
        logger.error("面试启动失败: {}", e)
        await _send_json(ws, {"type": "error", "message": f"面试启动失败: {e}"})
        return None

    # 保持长期记忆
    if not state.get("long_term_weaknesses"):
        state["long_term_weaknesses"] = long_term_weaknesses

    memory_manager.save_session(session_id, state)

    question = state.get("current_question_text", "")
    if not question:
        await _send_json(ws, {"type": "error", "message": "题目生成失败"})
        return None

    plan = state.get("question_plan", [])
    await _send_json(ws, {
        "type":            "question",
        "text":            question,
        "index":           int(state.get("current_question_idx", 0)) + 1,
        "total":           len(plan),
        "difficulty":      state.get("current_difficulty", "medium"),
        "jd_title":        state.get("jd_parsed", {}).get("title", ""),
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
    """处理用户回答"""
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
    snapshot = _build_short_term_snapshot(state)

    # ── 面试结束 ──────────────────────────────────────────────────────────
    if bool(state.get("interview_finished", False)):
        # ★ 如果 interviewer 没有生成结束语，主动生成一个
        farewell = state.get("agent_reply", "")
        if not farewell:
            farewell = "感谢你参与本次模拟面试！报告已生成，祝你面试顺利！"

        fresh_w = await _get_fresh_long_term(
            state.get("user_id", "web_user"),
            list(state.get("long_term_weaknesses", []))
        )
        snapshot["long_term_weaknesses"] = fresh_w

        await _send_json(ws, {
            "type":                   "finished",
            "farewell":               farewell,
            "report":                 state.get("final_report", {}),
            "study_plan":             state.get("study_plan", {}),
            "github_recommendations": state.get("github_recommendations", []),
            "memory_snapshot":        snapshot,
        })
        await _send_tts(ws, farewell, voice=voice)
        return state

    # ── 追问 ──────────────────────────────────────────────────────────────
    if bool(state.get("should_followup", False)):
        followup_q = state.get("current_question_text", "")
        await _send_json(ws, {
            "type":            "followup",
            "text":            followup_q,
            "memory_snapshot": snapshot,
        })
        await _send_tts(ws, followup_q, voice=voice)
        return state

    # ── 下一题 ────────────────────────────────────────────────────────────
    next_q = state.get("current_question_text", "")
    plan   = state.get("question_plan", [])
    await _send_json(ws, {
        "type":            "question",
        "text":            next_q,
        "index":           int(state.get("current_question_idx", 0)) + 1,
        "total":           len(plan),
        "difficulty":      state.get("current_difficulty", "medium"),
        "memory_snapshot": snapshot,
    })
    await _send_tts(ws, next_q, voice=voice)
    return state


async def _handle_force_finish(
    ws: WebSocket,
    state: Dict,
    graph,
) -> Dict:
    """强制结束面试，直接生成报告（跳过剩余题目）"""
    session_id = state.get("session_id", "")
    voice      = state.get("_voice")

    logger.info("强制结束面试: session={}", session_id)

    # 标记结束
    state["interview_finished"] = True
    state["force_finish"]       = True
    state["awaiting_evaluation"] = False

    # 如果当前题未作答，补一条空记录
    cur_q = state.get("current_question_text", "")
    if cur_q and not any(
        r.get("question") == cur_q
        for r in state.get("score_records", [])
    ):
        state.setdefault("score_records", []).append({
            "question": cur_q,
            "answer":   "（候选人主动结束，未作答）",
            "score": {
                "correctness": 0, "depth": 0, "structure": 0,
                "example": 0, "is_correct": False,
                "followup_needed": False, "key_missing": [],
            },
        })
        state["qa_history"] = state.get("qa_history", []) + [{
            "question": cur_q,
            "answer":   "（候选人主动结束，未作答）",
            "score":    {"is_correct": False},
        }]

    # 直接调节点函数，跳过 graph 路由
    try:
        from orchestration.nodes import (
            node_generate_report,
            node_study_plan,
            node_save_memory,
        )
        state = node_generate_report(state)
        state = node_study_plan(state)
        state = node_save_memory(state)
    except Exception as e:
        logger.error("强制结束生成报告失败: {}", e)
        await _send_json(ws, {"type": "error", "message": f"生成报告失败: {e}"})
        return state

    memory_manager.save_session(session_id, state)

    fresh_w = await _get_fresh_long_term(
        state.get("user_id", "web_user"),
        list(state.get("long_term_weaknesses", []))
    )
    snapshot = _build_short_term_snapshot(state)
    snapshot["long_term_weaknesses"] = fresh_w

    farewell = "面试已结束，感谢你的参与！评估报告已生成，请查看。"
    await _send_json(ws, {
        "type":                   "finished",
        "farewell":               farewell,
        "report":                 state.get("final_report", {}),
        "study_plan":             state.get("study_plan", {}),
        "github_recommendations": state.get("github_recommendations", []),
        "memory_snapshot":        snapshot,
    })
    await _send_tts(ws, farewell, voice=voice)
    return state


async def _handle_skill(
    ws: WebSocket,
    data: Dict[str, Any],
    state: Dict,
    graph,
) -> Dict:
    """处理技能调用"""
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

    graph      = _get_graph()
    state: Dict = memory_manager.load_session(session_id) or {}
    _alive     = True

    try:
        while _alive:
            try:
                message = await ws.receive()
            except Exception:
                break

            # 连接断开
            if message.get("type") == "websocket.disconnect":
                _alive = False
                break

            # ── 二进制音频（STT）─────────────────────────────────────────
            if "bytes" in message and message["bytes"]:
                audio_bytes = message["bytes"]
                logger.debug("收到音频帧: {} bytes", len(audio_bytes))
                # ★ 只识别，结果回传给前端填入输入框，不自动提交
                text = stt_engine.transcribe_bytes(audio_bytes, is_wav=False)
                await _send_json(ws, {
                    "type":    "stt_result",
                    "text":    text,
                    "message": "" if text else "未识别到语音，请重试",
                })
                continue

            # ── 文本 JSON 消息 ────────────────────────────────────────────
            raw_text = message.get("text", "")
            if not raw_text:
                continue

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                await _send_json(ws, {"type": "error", "message": "JSON 格式错误"})
                continue

            msg_type = data.get("type", "")

            # ping/pong 心跳
            if msg_type == "ping":
                await _send_json(ws, {"type": "pong"})

            # 启动面试
            elif msg_type == "start":
                result = await _handle_start(ws, data, session_id, graph)
                if result is not None:
                    state = result

            # 提交回答
            elif msg_type == "answer":
                if not state:
                    await _send_json(ws, {
                        "type": "error", "message": "请先发送 start 消息"
                    })
                    continue
                answer_text = data.get("text", "").strip()
                if not answer_text:
                    await _send_json(ws, {
                        "type": "error", "message": "回答不能为空"
                    })
                    continue
                state = await _handle_answer(ws, answer_text, state, graph)

            # 强制结束面试
            elif msg_type == "force_finish":
                if not state:
                    await _send_json(ws, {
                        "type": "error", "message": "请先发送 start 消息"
                    })
                    continue
                state = await _handle_force_finish(ws, state, graph)

            # 主动拉取记忆数据
            elif msg_type == "get_memory":
                user_id = (state.get("user_id", "web_user") if state
                           else data.get("user_id", "web_user"))
                if state:
                    await _send_memory_data(ws, state, user_id)
                else:
                    weaknesses = await _get_fresh_long_term(user_id, [])
                    await _send_json(ws, {
                        "type":       "memory_data",
                        "short_term": {
                            "qa_history": [],
                            "long_term_weaknesses": weaknesses,
                        },
                        "long_term": {"weaknesses": weaknesses},
                    })

            # 清除长期记忆
            elif msg_type == "clear_long_memory":
                user_id = (state.get("user_id", "web_user") if state
                           else data.get("user_id", "web_user"))
                ok = memory_manager.clear_weaknesses(user_id)
                if ok:
                    # 同步更新本地 state
                    if state:
                        state["long_term_weaknesses"] = []
                    # 推送更新后的记忆数据
                    snapshot = _build_short_term_snapshot(state) if state else {}
                    snapshot["long_term_weaknesses"] = []
                    await _send_json(ws, {
                        "type":       "memory_data",
                        "short_term": snapshot,
                        "long_term":  {"weaknesses": []},
                    })
                    await _send_json(ws, {
                        "type":  "toast",
                        "msg":   "长期记忆已清除 ✅",
                        "level": "success",
                    })
                else:
                    await _send_json(ws, {
                        "type":    "error",
                        "message": "清除失败，MySQL 可能不可用",
                    })

            # 查看 RAG 检索结果
            elif msg_type == "get_rag":
                if not state:
                    await _send_json(ws, {
                        "type": "error", "message": "请先开始面试"
                    })
                    continue
                rag_sources = state.get("rag_sources", [])
                rag_context = state.get("rag_context", "")
                await _send_json(ws, {
                    "type":        "rag_data",
                    "rag_sources": rag_sources[:10],
                    "rag_context": rag_context[:3000],
                    "total":       len(rag_sources),
                })

            # 手动朗读指定文本
            elif msg_type == "tts_speak":
                text_to_speak  = data.get("text", "").strip()
                voice_override = (data.get("voice") or
                                  (state.get("_voice") if state else None))
                logger.info(
                    "tts_speak: available={}, text_len={}, voice={}",
                    tts_engine.available,
                    len(text_to_speak),
                    voice_override,
                )
                await _send_tts(ws, text_to_speak, voice=voice_override)

            # 技能调用
            elif msg_type == "skill":
                if not state:
                    await _send_json(ws, {
                        "type": "error", "message": "请先发送 start 消息"
                    })
                    continue
                state = await _handle_skill(ws, data, state, graph)

            else:
                await _send_json(ws, {
                    "type":    "error",
                    "message": f"未知消息类型: {msg_type}",
                })

    except WebSocketDisconnect:
        _alive = False
        logger.info("WebSocket 断开: {}", session_id)
    except Exception as e:
        _alive = False
        logger.error("WebSocket 异常: {} {}", session_id, e)
    finally:
        if state:
            memory_manager.save_session(session_id, state)
        logger.info("WebSocket 连接关闭: {}", session_id)