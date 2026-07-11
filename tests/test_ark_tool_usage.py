import asyncio
from types import SimpleNamespace

import pytest

from llm_client.ark_client import ArkLLMClient


class _ResponsesAPI:
    def __init__(self, response):
        self.response = response

    async def create(self, **_kwargs):
        return self.response


def _client_for_response(response):
    client = object.__new__(ArkLLMClient)
    client.model = "test-model"
    client._client = SimpleNamespace(responses=_ResponsesAPI(response))
    return client


def _response_with_output(*items):
    assistant = SimpleNamespace(
        role="assistant",
        content=[SimpleNamespace(text="# Document")],
    )
    return SimpleNamespace(output=[*items, assistant])


@pytest.mark.parametrize(
    ("tool_item", "expected"),
    [
        (SimpleNamespace(type="web_search_call", status="completed"), True),
        (SimpleNamespace(type="web_search_call", status="incomplete"), False),
        (SimpleNamespace(type="web_search_call", status="in_progress"), False),
        (SimpleNamespace(type="other_tool_call", status="completed"), False),
    ],
)
def test_responses_with_tools_reports_only_completed_web_search_calls(
    tool_item, expected
):
    client = _client_for_response(_response_with_output(tool_item))

    result = asyncio.run(
        client.responses_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "web_search"}],
        )
    )

    assert str(result) == "# Document"
    completed_tool_types = getattr(result, "completed_tool_types", frozenset())
    assert ("web_search_call" in completed_tool_types) is expected
