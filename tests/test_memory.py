"""记忆系统测试"""
import pytest


@pytest.mark.skip(reason="需要 Redis + MySQL")
def test_short_term():
    from memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    print("Testing short-term memory...")
    print(stm.get_turns("test_session"))  # 应该是空的

    stm.append_turn("test_session", "user", "hello")
    turns = stm.get_turns("test_session")
    assert len(turns) >= 1
    print("Turns after appending:", turns)

    stm.clear("test_session")
    print("Turns after clearing:", stm.get_turns("test_session"))  # 应该是空的

    print("Short-term memory test passed!")

if __name__ == "__main__":
    test_short_term()

    # python -m tests.test_memory
    # pytest -s tests/test_memory.py