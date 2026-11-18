from app.llm.base import LLMMessage, ToolCall, to_openai_messages


def test_reasoning_content_is_passed_back_for_assistant() -> None:
    messages = [
        LLMMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),),
            reasoning_content="需要先查课堂",
        )
    ]
    payload = to_openai_messages(messages)
    assert payload[0]["reasoning_content"] == "需要先查课堂"
    assert payload[0]["tool_calls"][0]["function"]["name"] == "list_classrooms"


def test_reasoning_content_omitted_when_absent() -> None:
    payload = to_openai_messages([LLMMessage(role="assistant", content="结论")])
    assert "reasoning_content" not in payload[0]
