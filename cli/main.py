"""
CLI 入口：基于 typer + rich
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from config.logging import setup_logger

app    = typer.Typer(name="interview-agent", help="AI 模拟面试官 CLI")
console = Console()

SKILL_TRIGGERS = {
    "/quiz":    "quiz",
    "/teach":   "teach",
    "/project": "project",
    "/compare": "compare",
}

SKILL_HINT = (
    "\n[dim]💡 技能：/quiz <主题> 测验 | /teach <概念> 讲解 | "
    "/project <描述> 提炼亮点 | /compare <A> vs <B> 对比 | q 退出[/dim]"
)

FINISH_KEYWORDS = ("q", "quit", "exit", "退出", "结束面试", "结束", "end", "stop")


def _detect_skill(user_input: str):
    stripped = user_input.strip().lower()
    for prefix, skill_name in SKILL_TRIGGERS.items():
        if stripped.startswith(prefix):
            cleaned = user_input.strip()[len(prefix):].strip()
            return skill_name, cleaned
    return None


def _run_skill(graph, state: dict, skill_name: str, skill_input: str) -> dict:
    skill_state = dict(state)
    skill_state["intent"]     = "use_skill"
    skill_state["skill_name"] = skill_name
    skill_state["user_input"] = skill_input

    result = graph.invoke(skill_state)
    reply  = result.get("agent_reply", "")

    console.print(Panel(
        reply,
        title=f"🛠️  Skill: {skill_name}",
        border_style="magenta",
        padding=(1, 2),
    ))

    state["skill_state"] = result.get("skill_state", {})
    return state


def _ensure_list(val) -> list:
    """
    ★ 核心修复：确保字段为字符串列表，防止对字符串逐字遍历。
    - list  → 过滤空项
    - str   → 按分号/换行拆分为列表
    - other → 包装为单元素列表
    """
    if isinstance(val, list):
        return [str(i).strip() for i in val if str(i).strip()]
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return []
        import re
        parts = re.split(r"[；;\n]+", val)
        return [p.strip() for p in parts if p.strip()]
    return [str(val)] if val else []


def _print_report(report: dict) -> None:
    if not report:
        return

    rec_map = {
        "strong_hire": "[bold green]强烈推荐 ✅[/]",
        "hire":        "[green]推荐录用 ✅[/]",
        "weak_hire":   "[yellow]勉强推荐 ⚠️[/]",
        "no_hire":     "[red]不推荐 ❌[/]",
    }
    rec = rec_map.get(
        report.get("recommendation", ""),
        report.get("recommendation", "-")
    )

    console.print(Panel(
        f"[bold]总分：{report.get('overall_score', '-')} / 100[/]    "
        f"录用建议：{rec}\n\n"
        f"[bold cyan]📝 总评：[/]\n{report.get('summary', '')}\n\n"
        f"[bold cyan]💬 面试官寄语：[/]\n{report.get('interviewer_comment', '')}",
        title="📊 面试评估报告",
        border_style="cyan",
        padding=(1, 2),
    ))

    # ── 六维能力评分 ──────────────────────────────────────────────────────────
    dim_scores = report.get("dimension_scores", {})
    if dim_scores:
        dim_table = Table(
            title="🎯 六维能力评分",
            box=box.ROUNDED,
            border_style="blue",
            header_style="bold blue",
        )
        dim_table.add_column("能力维度",   style="cyan",    width=22)
        dim_table.add_column("得分",       justify="center", width=8)
        dim_table.add_column("评级",       justify="center", width=10)

        dim_name_map = {
            "technical_knowledge":  "技术知识掌握度",
            "problem_solving":      "问题解决能力",
            "system_design":        "系统设计能力",
            "communication":        "表达与沟通能力",
            "practical_experience": "实战经验丰富度",
            "learning_ability":     "学习潜力与适应力",
        }

        def _level(s):
            if not isinstance(s, (int, float)): return "-"
            if s >= 8: return "[green]优秀[/]"
            if s >= 6: return "[yellow]良好[/]"
            if s >= 4: return "[orange1]一般[/]"
            return "[red]待提升[/]"

        for key, cn in dim_name_map.items():
            s = dim_scores.get(key, "-")
            dim_table.add_row(cn, str(s), _level(s))
        console.print(dim_table)

    # ── 各主题表现 ────────────────────────────────────────────────────────────
    topic_perf = report.get("topic_performance", [])
    if topic_perf:
        tp_table = Table(
            title="📌 各技术主题表现",
            box=box.SIMPLE_HEAVY,
            border_style="blue",
            header_style="bold",
        )
        tp_table.add_column("主题",  style="cyan", width=20)
        tp_table.add_column("表现",  justify="center", width=10)
        tp_table.add_column("点评",  width=40)
        perf_map = {
            "good":    "[green]良好 ✅[/]",
            "average": "[yellow]一般 ➖[/]",
            "weak":    "[red]薄弱 ❌[/]",
        }
        for tp in topic_perf:
            perf = perf_map.get(tp.get("performance", ""), tp.get("performance", "-"))
            tp_table.add_row(
                tp.get("topic",   "-"),
                perf,
                tp.get("comment", "-"),
            )
        console.print(tp_table)

    # ── 优势 / 薄弱点 / 亮点 / 担忧 ─────────────────────────────────────────
    lines = []
    for label, color, key in [
        ("✅ 优势",     "green",   "strengths"),
        ("⚠️  薄弱点",  "red",     "weaknesses"),
        ("⭐ 亮点表现", "yellow",  "highlights"),
        ("🔍 关注点",   "magenta", "concerns"),
    ]:
        items = _ensure_list(report.get(key, []))
        if items:
            lines.append(f"[bold {color}]{label}：[/]")
            lines += [f"  • {it}" for it in items]
            lines.append("")

    if lines:
        console.print(Panel(
            "\n".join(lines),
            title="📋 详细分析",
            border_style="yellow",
            padding=(0, 2),
        ))


def _print_study_plan(study: dict) -> None:
    """
    打印复习计划。
    ★ 关键修复：practice_projects / mock_interview_tips 用 _ensure_list 保证是列表。
    """
    if not study:
        return

    lines   = []
    overall = study.get("overall_advice", "")
    if overall:
        lines.append(f"[bold cyan]💡 总体建议：[/]{overall}\n")

    for w in study.get("weeks", []):
        if not isinstance(w, dict):
            continue
        goals     = w.get("goals", "")
        resources = w.get("resources", "")
        # goals / resources 在 StudyPlannerAgent 已规范为字符串，直接展示
        if isinstance(goals, list):
            goals = "；".join(goals)
        if isinstance(resources, list):
            resources = "，".join(resources)

        lines.append(
            f"[bold]📅 第 {w.get('week', '-')} 周：{w.get('theme', '-')}[/]"
            f"（每天 {w.get('daily_hours', '-')} 小时）"
        )
        if goals:
            lines.append(f"  🎯 {goals}")
        if resources:
            lines.append(f"  📖 {resources}")
        lines.append("")

    # ★ 用 _ensure_list 确保是列表，彻底防止逐字遍历
    projects = _ensure_list(study.get("practice_projects", []))
    if projects:
        lines.append("[bold yellow]🔨 实战项目建议：[/]")
        for p in projects:
            lines.append(f"  • {p}")
        lines.append("")

    tips = _ensure_list(study.get("mock_interview_tips", []))
    if tips:
        lines.append("[bold green]🎤 面试技巧提示：[/]")
        for t in tips:
            lines.append(f"  • {t}")

    console.print(Panel(
        "\n".join(lines),
        title="📚 个性化复习计划",
        border_style="green",
        padding=(1, 2),
    ))


def _print_github_recommendations(recs: list) -> None:
    """
    打印 GitHub 学习资源推荐。
    ★ 修复：无论是否有结果都展示标题；无结果时展示友好提示。
    """
    if not recs:
        return

    console.print("\n[bold cyan]🔗 GitHub 学习资源推荐[/]")

    any_result = False
    for item in recs:
        weakness = item.get("weakness", "")
        repos    = item.get("repos", [])

        console.print(f"\n  [bold yellow]📚 针对薄弱点：{weakness}[/]")

        if not repos:
            console.print("  [dim]（未找到相关仓库，建议手动搜索）[/dim]")
            continue

        any_result = True
        repo_table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
            border_style="dim",
            padding=(0, 1),
        )
        repo_table.add_column("项目",     style="cyan",         width=35)
        repo_table.add_column("描述",                           width=36)
        repo_table.add_column("⭐ Stars", justify="right",      width=10)
        repo_table.add_column("语言",     justify="center",     width=12)

        for repo in repos:
            name = repo.get("name", "-")
            url  = repo.get("url",  "")
            desc = (repo.get("description") or "-")[:36]
            stars = repo.get("stars", 0)
            lang  = repo.get("language") or "-"

            repo_table.add_row(
                f"[link={url}]{name}[/link]" if url else name,
                desc,
                f"{stars:,}",
                lang,
            )
        console.print(repo_table)

    if not any_result:
        console.print(
            "\n  [dim]💡 GitHub API 可能因网络或限速无结果，"
            "建议配置 GITHUB_TOKEN 环境变量后重试[/dim]"
        )


@app.command()
def interview(
    jd: str = typer.Option(..., "--jd", help="岗位 JD 文本或文件路径"),
    resume: str | None = typer.Option(None, "--resume", help="简历文本或文件路径"),
    total_questions: int = typer.Option(5, "--total", help="出题数量"),
):
    """启动一场交互式模拟面试"""
    setup_logger()
    from orchestration.graph import get_compiled_graph
    from memory.memory_manager import memory_manager
    import uuid

    console.print(Panel.fit("[bold green]🎯 AI 模拟面试官[/]", border_style="green"))

    # ── 读取文件 ──────────────────────────────────────────────────────────────
    if jd.endswith((".txt", ".md")):
        jd = open(jd, encoding="utf-8").read()

    resume_text = ""
    if resume:
        if resume.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(resume)
            resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif resume.endswith((".txt", ".md")):
            resume_text = open(resume, encoding="utf-8").read()
        else:
            resume_text = resume

    session_id = str(uuid.uuid4())
    graph      = get_compiled_graph()

    # ── 阶段一：初始化 ────────────────────────────────────────────────────────
    init_state = {
        "session_id":            session_id,
        "user_id":               "cli_user",
        "jd_text":               jd,
        "resume_text":           resume_text,
        "intent":                "start_interview",
        "user_input":            "开始面试",
        "current_difficulty":    "medium",
        "current_question_idx":  0,
        "qa_history":            [],
        "score_records":         [],
        "awaiting_answer":       False,
        "awaiting_evaluation":   False,
        "interview_finished":    False,
        "should_followup":       False,
        "followup_count":        0,
        "max_followup":          2,
        "force_finish":          False,
        "skill_state":           {},
        "total_questions":       total_questions,   # ★ 写入 state
    }

    console.print(f"[yellow]正在分析 JD 和简历，生成 {total_questions} 道题目...[/]")
    state = graph.invoke(init_state)
    memory_manager.save_session(session_id, state)

    jd_parsed     = state.get("jd_parsed", {})
    question_plan = state.get("question_plan", [])
    total         = len(question_plan)

    console.print(
        f"\n[bold]📋 岗位：[/]{jd_parsed.get('title', '-')}  "
        f"[bold]共 {total} 题[/]\n"
    )

    first_q = state.get("current_question_text", "")
    if not first_q:
        console.print("[red]题目生成失败，请检查日志[/]")
        return

    cur_idx = state.get("current_question_idx", 0)
    console.print(f"[bold blue]【第 {cur_idx + 1}/{total} 题】[/] {first_q}")
    console.print(SKILL_HINT)

    # ── 阶段二：答题循环 ──────────────────────────────────────────────────────
    while not state.get("interview_finished", False):
        answer = Prompt.ask("\n[cyan]你的回答[/]")

        if answer.strip().lower() in FINISH_KEYWORDS:
            console.print("[yellow]面试中断，退出[/]")
            return

        # ── Skill 触发 ────────────────────────────────────────────────────────
        skill_result = _detect_skill(answer)
        if skill_result:
            skill_name, skill_input = skill_result
            state = _run_skill(graph, state, skill_name, skill_input)
            cur_q   = state.get("current_question_text", "")
            cur_idx = state.get("current_question_idx", 0)
            if cur_q:
                console.print(
                    f"\n[bold blue]【继续第 {cur_idx + 1}/{total} 题】[/] {cur_q}"
                )
            console.print(SKILL_HINT)
            continue

        # ── 正常答题 ──────────────────────────────────────────────────────────
        state["user_input"]          = answer
        state["last_user_answer"]    = answer
        state["intent"]              = "answer_question"
        state["awaiting_evaluation"] = True
        state["awaiting_answer"]     = False

        state = graph.invoke(state)
        memory_manager.save_session(session_id, state)

        # ── 面试结束 ──────────────────────────────────────────────────────────
        if state.get("interview_finished", False):
            farewell = state.get("agent_reply", "")
            if farewell:
                console.print(f"\n[bold red]💬 面试官：[/]{farewell}\n")
            break

        # ── 追问 ──────────────────────────────────────────────────────────────
        if state.get("should_followup", False):
            followup_q = state.get("current_question_text", "")
            if followup_q:
                console.print(f"\n[bold red]🔍 面试官追问：[/]{followup_q}")
            console.print(SKILL_HINT)
            continue

        # ── 下一题 ────────────────────────────────────────────────────────────
        next_q   = state.get("current_question_text", "")
        next_idx = state.get("current_question_idx", 0)
        if next_q:
            console.print(
                f"\n[bold blue]【第 {next_idx + 1}/{total} 题】[/] {next_q}"
            )
        console.print(SKILL_HINT)

    # ── 阶段三：报告 ──────────────────────────────────────────────────────────
    console.print("\n" + "─" * 60)
    _print_report(state.get("final_report", {}))
    _print_study_plan(state.get("study_plan", {}))
    _print_github_recommendations(state.get("github_recommendations", []))


@app.command()
def build_index(kb_dir: str = typer.Option("rag/knowledge_base", "--kb")):
    """构建 RAG 索引"""
    from rag.indexer import build_full_index
    setup_logger()
    build_full_index(kb_dir)


@app.command()
def check_env():
    """检查运行环境"""
    from scripts.check_env import check_all
    check_all()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
):
    """启动 Web 服务"""
    import uvicorn
    setup_logger()
    uvicorn.run("api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    print("111")
    app()