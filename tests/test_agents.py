"""Agent 单元测试"""
import pytest
from agents.intent_router import IntentRouterAgent
from agents.jd_analyzer import JDAnalyzerAgent


def test_intent_router_interview():
    agent = IntentRouterAgent()
    state = {"user_input": "/interview"}
    result = agent.run(state)
    print(result)
    assert result["intent"] == "start_interview"


def test_intent_router_chat():
    agent = IntentRouterAgent()
    state = {"user_input": "你好"}
    result = agent.run(state)
    print(result)
    assert result["intent"] in ("chat", "unknown")


@pytest.mark.skip(reason="需要 LLM API Key")
def test_jd_analyzer():
    agent = JDAnalyzerAgent()
    state = {"jd_text": "招聘 Python 后端工程师，要求熟悉 FastAPI、MySQL、Redis"}
    result = agent.run(state)
    print(result)
    assert "tech_stack" in result.get("jd_parsed", {})


if __name__ == "__main__":
    test_intent_router_interview()
    test_intent_router_chat()
    test_jd_analyzer()

    # 运行测试：pytest -v tests/test_agents.py
    # python -m tests.test_agents