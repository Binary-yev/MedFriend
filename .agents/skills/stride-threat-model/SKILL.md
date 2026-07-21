---
name: stride-threat-model
description: Performs a systematic STRIDE threat-modeling assessment of MedFriend's codebase and architecture, producing (or refreshing) threat_model.md. Use this when starting a new implementation phase, adding a tool or external integration, or reviewing existing components before deployment.
---

# STRIDE Threat Modeling Skill

## Goal
Guide the agent to analyze the workspace — directory structure, agent
instructions, tools, callbacks, deployment (Terraform), and configuration — and
produce or refresh a structured `threat_model.md` at the repository root.

MedFriend's attack surface is unusually large for an agent: it reads a patient's
mail, sends email, places phone calls, and launches a third-party MCP subprocess
via Node. Model each of those channels explicitly.

## Instructions

1. **Analyze system boundaries.** Map, from the actual code, the entry points and
   data flows before judging anything:
   - Transport: FastAPI + A2A endpoints (`care_navigator/fast_api_app.py`).
   - Reasoning core: the root `care_navigator` agent, its `AgentTool` sub-agents,
     and its 13 tools (`care_navigator/agent.py`).
   - Trust boundary — untrusted input: pasted text, uploaded PDFs/images, audio,
     and inbound email bodies are all attacker-controllable.
   - External systems: Gmail API (read+send), Bland.ai (calls), Google Maps MCP
     (npm subprocess).
   - Data at rest: the in-memory `CASE` (documents + quarantine), the Gmail
     `token.json`, API keys.
   - Observability: OpenTelemetry → Cloud Trace/Logging; optional GCS artifacts.

2. **Evaluate against the six STRIDE pillars.** For each, ask MedFriend-specific
   questions and find the mitigating code (or confirm its absence):
   - **Spoofing** — Is the caller authenticated before privileged tools
     (`send_mail`, `place_complaint_call`) run? Is each session bound to a
     verified principal, or is there a single global `CASE`?
   - **Tampering** — Can an untrusted document/email inject instructions or assert
     a false status? Trace the two-layer defense: the deterministic pre-filter
     (`care_navigator/security.py` → `screen_text`, wired via
     `_apply_security_prefilter` and `security_prefilter_callback`) and the
     model's semantic CLEAN/TAMPERED classification + quarantine store.
   - **Repudiation** — Are approvals, sends, calls, and quarantine transitions
     written to a durable append-only audit trail, or only to in-memory state?
   - **Information disclosure** — Is high-risk PII (SSN, card numbers) scrubbed
     before it reaches the model/logs? Are secrets kept out of git and out of
     trace spans? Is data minimized to each counterparty (Maps, the office)?
   - **Denial of service** — Are the FastAPI/A2A entry points and the outbound
     `send_mail` / `place_complaint_call` tools rate-limited or capped per
     session? (Phone calls carry real financial cost.)
   - **Elevation of privilege** — Can a tampered document escape quarantine? Does
     the Maps MCP subprocess get MedFriend's secrets, or a scoped env
     (`_scoped_maps_env`)? Can an unauthenticated caller reach privileged tools?

3. **Grade every threat against THIS codebase**, not against best practice in the
   abstract. Mark each mitigation with its real status:
   - ✅ **Implemented** — mitigated in committed code; cite the file/function.
   - 🟡 **Partial** — partially mitigated; state precisely what is and isn't done.
   - ⬜ **Recommended** — not yet done; state the accepted risk and the fix.
   A claim of ✅ that you cannot tie to a specific file/line is not ✅ — downgrade
   it. Never inflate a status; the document's value is that it is falsifiable.

4. **Output.** Write a highly structured `threat_model.md` to the repository root
   with: system boundaries, one section per STRIDE pillar (threat → status →
   mitigation), and a summary table. Preserve the existing document's status
   markers and citations; update only what changed in the code, and keep the
   README roadmap's open items in sync.
