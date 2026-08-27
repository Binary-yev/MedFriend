# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the CODE-ENFORCED approval gates.

`send_mail` and `place_complaint_call` are the only two tools with an
irreversible external side effect, so their approval gate is enforced by ADK's
`require_confirmation` rather than by the INSTRUCTION. These tests cover the
mechanism against a spy function (never the real Gmail/Bland calls) and then
assert the real agent is wired to use it.
"""

from types import SimpleNamespace

import pytest
from google.adk.tools import FunctionTool

from care_navigator import agent

# The tools that must never run without an explicit, out-of-band confirmation.
IRREVERSIBLE_TOOLS = {"send_mail", "place_complaint_call"}


def _tool_context(confirmation=None):
    """Minimal stand-in for the ToolContext FunctionTool.run_async touches."""
    return SimpleNamespace(
        tool_confirmation=confirmation,
        request_confirmation=lambda **kwargs: None,
        actions=SimpleNamespace(skip_summarization=False),
    )


# --------------------------------------------------------------------------- #
# 1. The mechanism, against a spy (no real side effects in play)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unconfirmed_call_never_reaches_the_function_body():
    """The whole point: no confirmation payload, no execution."""
    calls = []

    def dangerous_action(target: str) -> dict:
        calls.append(target)
        return {"sent": True}

    tool = FunctionTool(func=dangerous_action, require_confirmation=True)

    out = await tool.run_async(
        args={"target": "someone@example.com"}, tool_context=_tool_context()
    )

    assert "error" in out
    assert "confirmation" in out["error"].lower()
    # The body did not run. This is the assertion the security claim rests on.
    assert calls == []


@pytest.mark.asyncio
async def test_confirmed_call_executes():
    calls = []

    def dangerous_action(target: str) -> dict:
        calls.append(target)
        return {"sent": True}

    tool = FunctionTool(func=dangerous_action, require_confirmation=True)

    out = await tool.run_async(
        args={"target": "someone@example.com"},
        tool_context=_tool_context(SimpleNamespace(confirmed=True)),
    )

    assert out == {"sent": True}
    assert calls == ["someone@example.com"]


@pytest.mark.asyncio
async def test_rejected_call_is_refused():
    calls = []

    def dangerous_action(target: str) -> dict:
        calls.append(target)
        return {"sent": True}

    tool = FunctionTool(func=dangerous_action, require_confirmation=True)

    out = await tool.run_async(
        args={"target": "someone@example.com"},
        tool_context=_tool_context(SimpleNamespace(confirmed=False)),
    )

    assert out == {"error": "This tool call is rejected."}
    assert calls == []


# --------------------------------------------------------------------------- #
# 2. The real agent is wired to use it
# --------------------------------------------------------------------------- #
def _gated_tool_names():
    return {
        t.name
        for t in agent.root_agent.tools
        if isinstance(t, FunctionTool) and getattr(t, "_require_confirmation", False)
    }


def test_both_irreversible_tools_are_gated():
    assert _gated_tool_names() == IRREVERSIBLE_TOOLS


def test_no_other_tool_is_gated():
    """Keeps the gate list deliberate: a new gate has to be a conscious edit."""
    assert _gated_tool_names() <= IRREVERSIBLE_TOOLS


def test_wrapping_did_not_rename_or_drop_tools():
    """The eval trajectories and the model's declarations key off these names."""
    names = [t.name for t in agent.root_agent.tools if hasattr(t, "name")]

    assert len(agent.root_agent.tools) == 13
    for expected in IRREVERSIBLE_TOOLS:
        assert expected in names


def test_simulated_counterparties_have_no_tools_of_their_own():
    """Why only two gates: the sub-agents cannot act on the world.

    `insurance_reviewer` and `provider_office` role-play a reply and nothing
    else, so "submitting an appeal" internally and "booking" have no external
    effect to gate. If either ever gains a tool, that reasoning breaks and this
    test should fail loudly.
    """
    for sub_agent in (agent.insurance_reviewer, agent.provider_office):
        assert not getattr(sub_agent, "tools", None)
