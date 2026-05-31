"""
音频管理器：
- 格式转换（PCM <-> WAV）
- 采样率重采样
- 音频归一化
"""
from __future__ import annotations

import io
import wave
from math import gcd

import numpy as np
from loguru import logger

try:
    from scipy.signal import resample_poly
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False
    logger.warning("scipy 未安装，重采样功能不可用")


def pcm_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2,
) -> bytes:
    """
    PCM 原始字节 -> WAV 格式字节
    
    Args:
        pcm_bytes:   PCM 原始数据
        sample_rate: 采样率，默认 16000
        channels:    声道数，默认 1（单声道）
        sampwidth:   采样位宽（字节），默认 2（16-bit）
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf.getvalue()


def wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int]:
    """
    WAV -> PCM 原始字节
    
    Returns:
        (pcm_bytes, sample_rate, channels)
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sample_rate = wf.getframerate()
        channels    = wf.getnchannels()
        pcm_bytes   = wf.readframes(wf.getnframes())
    return pcm_bytes, sample_rate, channels


def wav_to_float32(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """
    WAV -> float32 numpy 数组（归一化到 [-1, 1]）
    
    Returns:
        (audio_array, sample_rate)
    """
    pcm_bytes, sample_rate, channels = wav_to_pcm(wav_bytes)
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    # 多声道转单声道
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sample_rate


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    音频重采样
    
    Args:
        audio:    float32 音频数组
        src_rate: 源采样率
        dst_rate: 目标采样率
    """
    if src_rate == dst_rate:
        return audio
    if not _SCIPY_AVAILABLE:
        logger.error("scipy 未安装，无法重采样，返回原始音频")
        return audio
    g = gcd(src_rate, dst_rate)
    return resample_poly(audio, dst_rate // g, src_rate // g).astype(np.float32)


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """音频归一化到 [-1, 1]"""
    max_val = np.max(np.abs(audio))
    if max_val < 1e-8:
        return audio
    return (audio / max_val).astype(np.float32)


def bytes_to_float32(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    is_wav: bool = False,
    target_rate: int = 16000,
) -> np.ndarray:
    """
    通用音频字节 -> float32 数组，自动处理重采样
    
    Args:
        audio_bytes:  音频字节（PCM 或 WAV）
        sample_rate:  PCM 模式下的采样率（WAV 模式自动读取）
        is_wav:       是否为 WAV 格式
        target_rate:  目标采样率（Whisper 需要 16000）
    """
    if is_wav:
        audio, src_rate = wav_to_float32(audio_bytes)
    else:
        audio    = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        src_rate = sample_rate

    if src_rate != target_rate:
        audio = resample(audio, src_rate, target_rate)

    return normalize_audio(audio)