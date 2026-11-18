from app.llm.base import LLMMessage, ToolCall
from app.runtime.context import ContextBuilder, estimate_tokens


def test_estimate_tokens_cjk_and_ascii() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("签到") == 2
    assert estimate_tokens("abcd") == 1


def test_short_context_is_unchanged() -> None:
    messages = [
        LLMMessage(role="system", content="规则"),
        LLMMessage(role="user", content="你好"),
    ]
    builder = ContextBuilder(token_budget=1000)
    assert builder.compact(messages) == messages


def test_long_context_is_compressed_within_budget() -> None:
    messages = [
        LLMMessage(role="system", content="规则" * 40),
        LLMMessage(role="user", content="查询签到"),
    ]
    for index in range(10):
        messages.append(
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id=f"c{index}", name="aggregate_stats", arguments={}),),
            )
        )
        messages.append(
            LLMMessage(
                role="tool",
                content="结果" * 2000,
                tool_call_id=f"c{index}",
                name="aggregate_stats",
            )
        )
    builder = ContextBuilder(token_budget=300, max_tool_result_chars=100)
    compacted = builder.compact(messages)
    assert builder.tokens(compacted) <= 300
    assert compacted[0].content.startswith("规则")
    assert compacted[1].role == "user"
    assert len(compacted) < len(messages)

def test_compaction_preserves_reasoning_content() -> None:
    messages = [
        LLMMessage(role="system", content="规则"),
        LLMMessage(role="user", content="查询"),
        LLMMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="c1", name="list_classrooms", arguments={}),),
            reasoning_content="需要先查课堂",
        ),
    ]
    builder = ContextBuilder(token_budget=10000)
    compacted = builder.compact(messages)
    assert compacted[2].reasoning_content == "需要先查课堂"
