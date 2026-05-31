"""
个性化复习计划 Agent：
- 基于评估报告薄弱点生成复习路径
- 调用 GitHub API 推荐开源学习资源
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import BaseAgent

SYSTEM_PROMPT = """\
你是技术学习规划师。基于候选人的面试薄弱点，生成一份 4 周复习计划。

面试评估报告：
__REPORT__

长期记忆（历史薄弱点）：
__HISTORY__

输出严格 JSON，字段说明：
- overall_advice：字符串，一句话总体建议
- weeks：数组，每个元素包含：
    week（数字）、theme（字符串）、goals（字符串，一句话目标）、
    daily_hours（数字）、resources（字符串，逗号分隔的资源列表）
- practice_projects：数组，每个元素是一个完整的项目建议字符串（不要拆分单个字）
- mock_interview_tips：数组，每个元素是一条完整的面试技巧字符串（不要拆分单个字）

示例格式：
{{
  "overall_advice": "加强实战经验积累",
  "weeks": [
    {{
      "week": 1,
      "theme": "系统设计",
      "goals": "掌握分布式系统核心概念",
      "daily_hours": 2,
      "resources": "《设计数据密集型应用》, Designing Data-Intensive Applications"
    }}
  ],
  "practice_projects": [
    "构建一个完整的RAG问答系统，包含文档解析、向量检索和答案生成",
    "实现一个支持多路召回的混合检索引擎"
  ],
  "mock_interview_tips": [
    "回答技术问题时先说结论再展开细节",
    "准备3个能体现系统思维的项目案例"
  ]
}}
"""


def _ensure_list(val: Any) -> List[str]:
    """
    确保字段为字符串列表：
    - 已是列表 → 过滤空项后返回
    - 字符串 → 按分号或换行拆分
    - 其他 → 转 str 后包装为单元素列表
    """
    if isinstance(val, list):
        result = []
        for item in val:
            s = str(item).strip()
            if s:
                result.append(s)
        return result
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return []
        # 按中文分号、英文分号、换行拆分
        import re
        parts = re.split(r"[；;\n]+", val)
        return [p.strip() for p in parts if p.strip()]
    return [str(val)] if val else []


class StudyPlannerAgent(BaseAgent):
    name = "study_planner"
    description = "个性化复习计划 + GitHub 资源推荐"

    def _fetch_github_resources(
        self, weaknesses: List[str]
    ) -> List[Dict[str, Any]]:
        """为每个薄弱点搜索 GitHub 学习资源"""
        from mcp.tools.github_tool import search_learning_repos

        github_recs = []
        for weakness in weaknesses[:5]:   # 最多处理5个薄弱点
            try:
                repos = search_learning_repos(weakness, max_results=3)
                if repos:
                    github_recs.append({"weakness": weakness, "repos": repos})
                    self.logger.info(
                        "GitHub 搜索成功：{} → {} 个仓库", weakness, len(repos)
                    )
                else:
                    self.logger.warning("GitHub 搜索无结果：{}", weakness)
                    github_recs.append({"weakness": weakness, "repos": []})
            except Exception as e:
                self.logger.warning("GitHub 搜索异常：{} → {}", weakness, e)
                github_recs.append({"weakness": weakness, "repos": []})
        return github_recs

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        report  = state.get("final_report", {})
        history = state.get("long_term_weaknesses", [])

        prompt = (
            SYSTEM_PROMPT
            .replace("__REPORT__",  str(report)[:3000])
            .replace("__HISTORY__", str(history)[:500])
        )

        parsed = self.invoke_llm_json(prompt, "")

        # ★ 规范化所有字段，防止 LLM 返回字符串导致逐字遍历
        weeks = parsed.get("weeks", [])
        if isinstance(weeks, list):
            for w in weeks:
                if isinstance(w, dict):
                    # goals 和 resources 统一为字符串（显示用）
                    if isinstance(w.get("goals"), list):
                        w["goals"] = "；".join(w["goals"])
                    if isinstance(w.get("resources"), list):
                        w["resources"] = "，".join(w["resources"])

        parsed["practice_projects"]   = _ensure_list(parsed.get("practice_projects",   []))
        parsed["mock_interview_tips"] = _ensure_list(parsed.get("mock_interview_tips", []))
        parsed["weeks"]               = weeks

        state["study_plan"] = parsed

        # ── GitHub 资源推荐 ────────────────────────────────────────────────────
        weaknesses = report.get("weaknesses", [])
        if not weaknesses:
            weaknesses = state.get("weaknesses_to_remember", [])

        github_recs = self._fetch_github_resources(weaknesses)
        state["github_recommendations"] = github_recs

        return state