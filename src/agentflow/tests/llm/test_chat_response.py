"""Unit tests for ChatResponse value objects."""

from __future__ import annotations

import pytest
from git_root_to_syspath import agr

agr()

from src.agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo


# ---------------------------------------------------------------------------
# UsageInfo
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUsageInfo:
    def test_str_contains_all_counts(self) -> None:
        u = UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        s = str(u)
        assert "10" in s and "20" in s and "30" in s

    def test_total_tokens_value(self) -> None:
        u = UsageInfo(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        assert u.total_tokens == 10


# ---------------------------------------------------------------------------
# ChatResponse — properties
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChatResponseProperties:
    def _make(
        self,
        content: str | None = None,
        tool_calls: list[ToolCallInfo] | None = None,
    ) -> ChatResponse:
        return ChatResponse(role="assistant", content=content, tool_calls=tool_calls, usage=None)

    def test_text_returns_content_string(self) -> None:
        r = self._make(content="Hello")
        assert r.text == "Hello"

    def test_text_returns_empty_string_when_no_content(self) -> None:
        r = self._make(content=None)
        assert r.text == ""

    def test_has_tool_calls_false_when_none(self) -> None:
        r = self._make()
        assert not r.has_tool_calls

    def test_has_tool_calls_true_when_present(self) -> None:
        tc = ToolCallInfo(
            id="call-1",
            function=ToolCallFunction(name="calc", arguments='{"x": 1}'),
        )
        r = self._make(tool_calls=[tc])
        assert r.has_tool_calls


# ---------------------------------------------------------------------------
# to_message_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToMessageDict:
    def test_plain_text_response_serialises_correctly(self) -> None:
        r = ChatResponse(role="assistant", content="Hi", tool_calls=None, usage=None)
        d = r.to_message_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi"
        assert "tool_calls" not in d

    def test_tool_call_response_includes_tool_calls(self) -> None:
        tc = ToolCallInfo(
            id="call-42",
            function=ToolCallFunction(name="get_weather", arguments='{"city":"Prague"}'),
        )
        r = ChatResponse(role="assistant", content=None, tool_calls=[tc], usage=None)
        d = r.to_message_dict()
        assert "tool_calls" in d
        assert d["tool_calls"][0]["id"] == "call-42"
        assert d["tool_calls"][0]["function"]["name"] == "get_weather"

    def test_extra_fields_preserved_in_serialisation(self) -> None:
        tc = ToolCallInfo(
            id="call-1",
            function=ToolCallFunction(
                name="fn", arguments="{}", extra={"thought_signature": "abc123"}
            ),
            extra={"index": 0},
        )
        r = ChatResponse(role="assistant", content=None, tool_calls=[tc], usage=None)
        d = r.to_message_dict()
        fn = d["tool_calls"][0]["function"]
        assert fn["thought_signature"] == "abc123"
        assert d["tool_calls"][0]["index"] == 0

    def test_no_content_key_when_content_is_none(self) -> None:
        r = ChatResponse(role="assistant", content=None, tool_calls=None, usage=None)
        assert "content" not in r.to_message_dict()


# ---------------------------------------------------------------------------
# ToolCallInfo convenience accessors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tool_call_info_name_and_arguments_accessors() -> None:
    tc = ToolCallInfo(
        id="x",
        function=ToolCallFunction(name="my_tool", arguments='{"a": 1}'),
    )
    assert tc.name == "my_tool"
    assert tc.arguments == '{"a": 1}'
