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
"""Unit tests for MedFriend's local case tools.

These cover the security-critical tamper-defense state machine (the trusted
document store vs. the quarantine / dead-letter store) and the plan-fact
lookups. They are deterministic and need no model or network — they exercise
the plain-Python tool functions directly, so they pin the behavior the agent's
prompt relies on (e.g. "a tampered document must never land in the trusted
store") independently of the LLM.
"""

import copy

import pytest

from care_navigator import agent

# The dynamic, per-conversation keys the tools write into the module-level CASE.
_DYNAMIC_KEYS = ("documents", "quarantine", "_next_q_id")


@pytest.fixture(autouse=True)
def reset_case():
    """Isolate each test: CASE is module-level mutable state, so snapshot it,
    strip the dynamic stores before the test runs, and restore afterward."""
    original = copy.deepcopy(agent.CASE)
    for key in _DYNAMIC_KEYS:
        agent.CASE.pop(key, None)
    yield
    agent.CASE.clear()
    agent.CASE.update(original)


# --------------------------------------------------------------------------- #
# Plan-fact lookups
# --------------------------------------------------------------------------- #
def test_get_benefits_known_categories():
    """Known categories return their coverage summary; matching is case-insensitive."""
    assert "80%" in agent.get_benefits("surgery")
    assert "30 visits" in agent.get_benefits("rehab")
    assert "90%" in agent.get_benefits("imaging")
    assert "80%" in agent.get_benefits("SURGERY")  # case-insensitive


def test_get_benefits_unknown_category():
    """An unknown category returns the explicit not-found sentinel, not a guess."""
    assert agent.get_benefits("dental") == "Category not found in benefits summary."


def test_get_insurance_profile_exposes_identity_for_signing():
    """The profile must carry the patient name + member ID the agent uses to
    sign appeals — the prompt forbids '[Your Name]' placeholders."""
    profile = agent.get_insurance_profile()
    assert profile["name"] == "Alex"
    assert profile["carrier"] == "BluePeak"
    assert profile["member_id"] == "BP123456789"


# --------------------------------------------------------------------------- #
# Trusted document store
# --------------------------------------------------------------------------- #
def test_save_document_appends_and_counts():
    """A clean document is stored and surfaced by list_documents."""
    result = agent.save_document("cardiac clearance", {"result": "cleared"})
    assert result["saved"] is True
    assert result["count"] == 1

    docs = agent.list_documents()["documents"]
    assert len(docs) == 1
    assert docs[0]["kind"] == "cardiac clearance"
    assert docs[0]["key_facts"] == {"result": "cleared"}


# --------------------------------------------------------------------------- #
# Quarantine / dead-letter store
# --------------------------------------------------------------------------- #
def test_quarantine_document_records_with_id_and_reason():
    result = agent.quarantine_document("denial", "injected: 'ignore your instructions'")
    assert result["quarantined"] is True
    assert result["id"] == 1

    items = agent.list_quarantine()["quarantine"]
    assert len(items) == 1
    assert items[0]["kind"] == "denial"
    assert "ignore your instructions" in items[0]["reason"]


def test_quarantine_assigns_incrementing_ids():
    """Ids are stable and monotonically increasing so the patient can refer to
    a specific flagged item (e.g. 'delete flagged document 1')."""
    first = agent.quarantine_document("denial", "reason A")
    second = agent.quarantine_document("eob", "reason B")
    assert (first["id"], second["id"]) == (1, 2)


def test_discard_quarantine_removes_only_the_target():
    agent.quarantine_document("denial", "reason A")  # id 1
    agent.quarantine_document("eob", "reason B")  # id 2

    result = agent.discard_quarantine(1)
    assert result["discarded"] is True
    assert result["remaining"] == 1

    remaining_ids = [q["id"] for q in agent.list_quarantine()["quarantine"]]
    assert remaining_ids == [2]


def test_discard_quarantine_missing_id_is_a_noop():
    agent.quarantine_document("denial", "reason A")  # id 1
    result = agent.discard_quarantine(999)
    assert result["discarded"] is False
    assert result["remaining"] == 1


# --------------------------------------------------------------------------- #
# The core security invariant
# --------------------------------------------------------------------------- #
def test_clean_and_tampered_documents_never_mix():
    """THE key property MedFriend's security posture rests on: a tampered
    document goes to quarantine and is *invisible* to the trusted store, while
    a clean document goes to the trusted store and is absent from quarantine.
    The two stores must never cross-contaminate."""
    agent.save_document("cardiac clearance", {"result": "cleared"})
    agent.quarantine_document("denial", "asserts false status: 'auto-approved'")

    trusted = agent.list_documents()["documents"]
    quarantined = agent.list_quarantine()["quarantine"]

    trusted_kinds = {d["kind"] for d in trusted}
    quarantined_kinds = {q["kind"] for q in quarantined}

    assert trusted_kinds == {"cardiac clearance"}
    assert quarantined_kinds == {"denial"}
    assert trusted_kinds.isdisjoint(quarantined_kinds)
