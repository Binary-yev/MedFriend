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

"""Deterministic, code-level security primitives — MedFriend's first line of defense.

MedFriend defends against prompt injection in two complementary layers:

  Layer 1 (this module) — DETERMINISTIC. Pure regex/keyword screening that runs
    in Python *before* untrusted text reaches the model. It cannot be talked out
    of a decision by clever wording, because it is not a model — it is code. It
    catches the unambiguous, well-known attack strings and redacts high-risk PII
    (SSNs, payment-card numbers) so those tokens never flow into the LLM or logs.

  Layer 2 (the agent's INSTRUCTION + quarantine store, in agent.py) — SEMANTIC.
    The model classifies each document CLEAN vs TAMPERED and routes tampered
    content to a quarantine / dead-letter store that is invisible to downstream
    reasoning. This catches novel or subtly-phrased injections that a fixed
    keyword list would miss.

The two layers are deliberately different in kind: Layer 1 is robust but rigid;
Layer 2 is flexible but probabilistic. Together they are belt-and-suspenders. The
design of Layer 1 is adapted from the sibling `ambient-expense-agent` project's
pre-LLM security checkpoint and hardened for MedFriend's threat surface.

Everything here is a pure function with no I/O, so it is fast and exhaustively
unit-testable (see tests/unit/test_security.py) without a model or network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------
# We redact only *high-sensitivity identity/financial* tokens that must never
# reach an LLM or a log sink. We deliberately do NOT scrub the patient's own
# email address, phone number, or insurance member ID: those are operational
# data the care-navigation workflows legitimately need (e.g. replying to a
# denial email, signing an appeal with the member ID). Over-scrubbing would
# break the very tasks MedFriend exists to perform.
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_16_RE = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b")  # Visa/MC/Discover
_CC_15_RE = re.compile(r"\b\d{4}[- ]?\d{6}[- ]?\d{5}\b")  # Amex

# ---------------------------------------------------------------------------
# Prompt-injection signatures
# ---------------------------------------------------------------------------
# Substring signatures for the UNAMBIGUOUS injection phrases — the ones a real
# patient would essentially never type, but that appear in tampered documents
# trying to hijack the agent. We intentionally leave AMBIGUOUS phrases (e.g.
# "forward this", "send this to X") OUT of the deterministic list: those can be
# legitimate user requests, so they are left to Layer 2's semantic judgment.
# This keeps the deterministic layer high-precision (few false positives) while
# the model handles the fuzzy, context-dependent cases.
INJECTION_PATTERNS: tuple[str, ...] = (
    # "ignore/override/bypass your instructions" family
    "ignore your instructions",
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore above instructions",
    "ignore the rules",
    "disregard your instructions",
    "disregard previous instructions",
    "disregard the above",
    "override the rules",
    "override your instructions",
    "bypass the rules",
    "bypass your instructions",
    "change the rules",
    "new instruction:",
    "system prompt",
    # forced-approval / skip-review family (MedFriend + expense overlap)
    "auto-approve",
    "auto-approved",
    "force approval",
    "force auto-approval",
    "you must approve",
    "do not review",
    "skip review",
    "instead of reviewing",
    # quarantine-release family (MedFriend-specific: attacker trying to escape
    # the dead-letter store from inside a document)
    "un-quarantine",
    "unquarantine",
    "release the quarantine",
    "release from quarantine",
    "trust this document",
)


@dataclass
class ScreenResult:
    """Outcome of screening one piece of untrusted text.

    Attributes:
        clean_text: The input with high-risk PII redacted (safe to forward/log).
        redacted_categories: Which PII categories were redacted (e.g. ["SSN"]).
        injection_detected: True if any deterministic injection signature matched.
        matched_patterns: The specific signatures that matched (for audit/logging).
    """

    clean_text: str
    redacted_categories: list[str] = field(default_factory=list)
    injection_detected: bool = False
    matched_patterns: list[str] = field(default_factory=list)


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Redact SSNs and payment-card numbers from ``text``.

    Returns the redacted text and the list of PII categories that were found and
    replaced. Idempotent: running it twice yields the same result. Non-matching
    text is returned unchanged with an empty category list.
    """
    if not text:
        return text, []

    redacted: list[str] = []

    if _SSN_RE.search(text):
        text = _SSN_RE.sub("[REDACTED SSN]", text)
        redacted.append("SSN")

    has_cc = False
    if _CC_16_RE.search(text):
        text = _CC_16_RE.sub("[REDACTED CARD]", text)
        has_cc = True
    if _CC_15_RE.search(text):
        text = _CC_15_RE.sub("[REDACTED CARD]", text)
        has_cc = True
    if has_cc:
        redacted.append("PaymentCard")

    return text, redacted


def detect_prompt_injection(text: str) -> tuple[bool, list[str]]:
    """Deterministically check ``text`` for known injection signatures.

    Case-insensitive substring match against ``INJECTION_PATTERNS``. Returns
    (True, [matched signatures]) if any matched, else (False, []). This is a
    high-precision detector, not a complete one — subtle/novel injections are
    caught by the model's semantic classification (Layer 2), not here.
    """
    if not text:
        return False, []
    lowered = text.lower()
    matches = [p for p in INJECTION_PATTERNS if p in lowered]
    return (len(matches) > 0), matches


def screen_text(text: str) -> ScreenResult:
    """Run the full deterministic screen: PII redaction + injection detection.

    This is the single entry point the agent uses. Injection detection runs on
    the ORIGINAL text (so a redaction can never hide an attack phrase), while the
    returned ``clean_text`` is the PII-redacted version safe to pass downstream.
    """
    injection_detected, matched = detect_prompt_injection(text)
    clean_text, redacted = scrub_pii(text)
    return ScreenResult(
        clean_text=clean_text,
        redacted_categories=redacted,
        injection_detected=injection_detected,
        matched_patterns=matched,
    )
