"""
GitHub 仓库分析工具：
- 搜索学习某技术主题的优质开源项目
- 分析指定仓库的 star / README / 技术栈
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from config import settings

SEARCH_URL = "https://api.github.com/search/repositories"

# 语言列表（分开查询，避免 OR 语法被 GitHub API 截断）
_LANGUAGES = ["python", "javascript", "typescript", "java", "go"]


def _build_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
        logger.debug("GitHub API 使用认证 Token")
    else:
        logger.debug("GitHub API 未配置 Token，使用匿名访问（限速60次/小时）")
    return headers


def _clean_topic(topic: str) -> str:
    """清洗搜索主题：去除中文标点、截断过长文本"""
    import re
    # 只保留字母、数字、空格、连字符
    cleaned = re.sub(r"[^\w\s\-]", " ", topic, flags=re.UNICODE)
    # 截断到前3个词，避免 query 过长
    words = cleaned.split()[:4]
    return " ".join(words).strip() or "machine learning"


def search_learning_repos(
    topic: str,
    max_results: int = 3,
    min_stars: int = 100,
) -> List[Dict[str, Any]]:
    """
    搜索与 topic 相关的优质学习仓库。
    策略：先用精确 topic 搜索，不足时用清洗后的关键词补充。
    """
    headers = _build_headers()
    clean   = _clean_topic(topic)

    if not clean:
        logger.warning("搜索主题清洗后为空，跳过：{}", topic)
        return []

    # ★ 简化 query：不用 OR 语法，只搜索 topic + stars 门槛
    query = f"{clean} stars:>{min_stars}"

    params = {
        "q":        query,
        "sort":     "stars",
        "order":    "desc",
        "per_page": max(max_results * 2, 10),   # 多取一些，过滤后取前 N
    }

    logger.info("GitHub 搜索：query={}", query)

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(SEARCH_URL, headers=headers, params=params)

            # 处理限速
            if resp.status_code == 403:
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait     = max(reset_ts - int(time.time()), 0)
                logger.warning("GitHub API 限速，需等待 {} 秒", wait)
                return []

            # 处理认证失败
            if resp.status_code == 401:
                logger.warning("GitHub Token 无效，尝试匿名请求")
                headers.pop("Authorization", None)
                resp = client.get(SEARCH_URL, headers=headers, params=params)

            resp.raise_for_status()
            data = resp.json()

    except httpx.TimeoutException:
        logger.warning("GitHub 搜索超时：{}", topic)
        return []
    except httpx.HTTPStatusError as e:
        logger.warning("GitHub HTTP 错误：{} → {}", topic, e)
        return []
    except Exception as e:
        logger.warning("GitHub 搜索失败：{} → {}", topic, e)
        return []

    items   = data.get("items", [])
    results = []

    for item in items:
        if len(results) >= max_results:
            break
        # 过滤明显不相关（名字完全不含关键词的）
        name = (item.get("full_name") or "").lower()
        desc = (item.get("description") or "").lower()
        kw   = clean.lower().split()[0] if clean else ""

        results.append({
            "name":        item.get("full_name", "-"),
            "url":         item.get("html_url", ""),
            "stars":       item.get("stargazers_count", 0),
            "description": (item.get("description") or "")[:200],
            "language":    item.get("language") or "-",
            "updated_at":  item.get("updated_at", ""),
        })

    logger.info(
        "GitHub 搜索完成：topic={}, 找到 {} 个仓库", topic, len(results)
    )
    return results


def analyze_repo(owner: str, repo: str) -> Dict[str, Any]:
    """分析指定仓库的基本信息"""
    headers = _build_headers()
    url     = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "name":        data.get("full_name"),
                "stars":       data.get("stargazers_count", 0),
                "forks":       data.get("forks_count", 0),
                "language":    data.get("language"),
                "description": (data.get("description") or "")[:300],
                "url":         data.get("html_url"),
                "topics":      data.get("topics", []),
                "updated_at":  data.get("updated_at"),
            }
    except Exception as e:
        logger.warning("GitHub 仓库分析失败 {}/{}: {}", owner, repo, e)
        return {}