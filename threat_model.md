# STRIDE Threat Model: MedFriend (MedNav Care-Navigation Agent)

This document is a systematic [STRIDE](https://en.wikipedia.org/wiki/STRIDE_model)
threat-modeling assessment of MedFriend. Unlike a checklist of aspirational
fixes, each threat below is marked with the status of its mitigation in **this
codebase**: ✅ **Implemented**, 🟡 **Partial**, or ⬜ **Recommended**. MedFriend's
attack surface is unusually large for an agent — it reads a patient's mail,
sends email, places phone calls, and launches a third-party MCP subprocess — so
the analysis is correspondingly detailed.

---

## System boundaries & architecture

- **Client / transport:** FastAPI endpoints (`/run_sse`, `/apps/care_navigator/...`,
  `/feedback`) and A2A JSON-RPC + agent card (`/a2a/care_navigator/...`), served
  by `care_navigator/fast_api_app.py`.
- **Agent engine:** the root `care_navigator` agent (Gemini 2.5 Flash) with 13
  tools, plus two `AgentTool` sub-agents (`insurance_reviewer`, `provider_office`).
- **Trust boundary — untrusted input:** pasted text, uploaded PDFs/images, audio,
  and **inbound email bodies** are all attacker-controllable content.
- **External systems:** Gmail API (read + send, patient OAuth), Bland.ai
  (outbound phone calls), and the Google Maps **MCP server** (an npm package run
  via `npx` as a subprocess).
- **Data at rest:** the in-memory `CASE` (trusted documents + quarantine), the
  Gmail OAuth `token.json`, and API keys (from env / git-ignored files).
- **Observability:** OpenTelemetry → Cloud Trace / Cloud Logging; optional GCS
  artifacts.

---

## STRIDE analysis

### 1. Spoofing (identity)

- **Threat:** The FastAPI / A2A endpoints do not themselves authenticate the
  caller. Anyone with network access can converse as "the patient" and trigger
  privileged tools (send email, place a call). The agent has no notion of a
  verified principal — there is a single global `CASE`.
- **Status:** 🟡 **Partial.** The provided Terraform (`deployment/terraform/`)
  defaults the Cloud Run service to **requiring an authenticated invoker** — the
  public `allUsers` binding is deliberately commented out in `iam.tf`, so IAM
  authentication is enforced at the platform layer out of the box. What is not
  yet done is binding each *session* to that authenticated principal (there is
  still a single global `CASE`), so this is Partial rather than Implemented.
- **Mitigation:** Keep the authenticated-invoker default (or front it with IAP /
  an OAuth2 proxy); additionally bind each session to the authenticated principal
  and never trust a user- or document-supplied identity. *(The agent already
  refuses to let a document assert identity or status — see Tampering.)*

### 2. Tampering (data & state integrity)

- **Threat 2a — prompt injection:** An untrusted document (pasted, PDF, image,
  audio, or email) embeds instructions to hijack the agent ("ignore your
  instructions", "auto-approve", "email X to Y") or asserts a false status.
- **Status:** ✅ **Implemented (defense in depth).**
- **Mitigation:**
  - *Layer 1 — deterministic (`care_navigator/security.py`):* regex/keyword
    screening redacts PII and flags known injection signatures **in code, before
    the model runs**, on the email channel (`check_new_mail` →
    `_apply_security_prefilter`) and the pasted-text channel (the root agent's
    `before_model_callback`).
  - *Layer 2 — semantic (the `INSTRUCTION` + quarantine store):* the model
    classifies each document CLEAN vs TAMPERED and routes tampered content to a
    dead-letter store that is invisible to downstream reasoning.
  - Approval gates ensure even a *missed* injection cannot cause an autonomous
    real-world action.
- **Threat 2b — shared mutable state:** `CASE` (case + documents + quarantine)
  is a process-wide, in-memory dict. Concurrent users would read/overwrite each
  other's data, and all state is lost on restart.
- **Status:** ⬜ **Recommended** (accepted for the demo; see README roadmap).
- **Mitigation:** Move the case, document, and quarantine stores into per-session
  ADK state backed by a persistent, per-user datastore.

### 3. Repudiation (audit trail)

- **Threat:** Approvals, sent emails, placed calls, and quarantine
  discard/release decisions modify in-memory state (and stdout) but are not
  written to a durable, append-only audit log. A patient could dispute "I never
  approved that appeal," and an operator cannot reconstruct who did what.
- **Status:** 🟡 **Partial.** OpenTelemetry (Cloud Trace/Logging) plus the
  Terraform **BigQuery sinks** for GenAI-telemetry and `/feedback` logs give a
  durable, queryable trail — but there is still no dedicated append-only log
  scoped to *actions* (approvals, sends, calls, quarantine transitions).
- **Mitigation:** Write an append-only audit record (Cloud Logging with
  retention, or BigQuery) for every outbound action and every quarantine
  transition, capturing timestamp, action, approver, and recipient.

### 4. Information disclosure

- **Threat 4a — PII to model/logs:** SSNs or payment-card numbers inside a
  document or email could flow into the LLM prompt, traces, or logs.
- **Status:** ✅ **Implemented.** Deterministic PII scrubbing
  (`care_navigator/security.py`) runs on both untrusted channels before the
  model sees the text, and telemetry is configured to keep prompt/response
  content **out** of trace spans (`app_utils/telemetry.py`,
  `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` / `NO_CONTENT`).
- **Threat 4b — secret leakage:** Committing the Gmail token, Maps/Bland keys, or
  GCP credentials.
- **Status:** ✅ **Implemented.** No secrets are committed (verified in the
  working tree *and* git history); secrets load from env vars / git-ignored file
  paths; `.gitignore` covers `token.json`, `credentials.json`, `api_key.txt`,
  `*.pem`, `*-key.json`; pre-commit `detect-secrets` + `detect-private-key` add a
  commit-time backstop. In the Terraform deployment, runtime secrets are injected
  from **Secret Manager** (the Gmail token mounted read-only as `token.json`, the
  Bland.ai and Maps keys as secret env vars) rather than baked into the image.
- **Threat 4c — over-sharing to counterparties:** Sending patient health details
  to the scheduling office, or patient identity to the Maps search.
- **Status:** ✅ **Implemented.** Data-minimization rules in the `INSTRUCTION`
  send only location + specialty to Maps and only scheduling details to the
  office, and reply only to the original denial sender.
- **Threat 4d — stack-trace leakage:** Raw tracebacks in FastAPI 500 responses
  could reveal internals.
- **Status:** ⬜ **Recommended.** Add a global exception handler that strips
  tracebacks from HTTP 500s.

### 5. Denial of service

- **Threat:** There is no rate limiting on the FastAPI / A2A entry points or on
  the outbound `send_mail` / `place_complaint_call` tools. An attacker (or a
  runaway loop) could exhaust the Gemini quota, spam emails, or place many phone
  calls — the last of which carries real financial cost and could harass a third
  party.
- **Status:** 🟡 **Partial.** Approval gates prevent *unattended* outbound
  actions, and the model has bounded retries — but there is no hard rate limit.
- **Mitigation:** Add rate-limiting middleware (e.g. `slowapi`) at the FastAPI
  entry points and enforce per-session caps on `send_mail` and
  `place_complaint_call`.

### 6. Elevation of privilege

- **Threat 6a — quarantine escape:** A tampered document instructs the agent to
  release or trust quarantined content ("un-quarantine", "trust this document"),
  attempting to promote untrusted data into a trusted action.
- **Status:** ✅ **Implemented.** The quarantine HARD RULE forbids self-release;
  a flagged item can only be cleared by re-running a *fresh clean copy* through
  intake. The deterministic Layer-1 filter additionally flags the
  `un-quarantine` / `trust this document` signatures.
- **Threat 6b — MCP subprocess over-privilege (supply chain):** The Google Maps
  MCP server is third-party npm code launched via `npx`. If handed the full
  process environment, a compromised version could read MedFriend's own secrets
  (Bland key, Gmail token path, GCP creds).
- **Status:** ✅ **Implemented.** `_scoped_maps_env()` strips MedFriend's
  sensitive keys and passes the subprocess only `GOOGLE_MAPS_API_KEY`. The server
  itself is installed from a committed, integrity-locked lockfile (`package.json`
  + `package-lock.json`, installed with `npm ci`) and launched directly from
  `node_modules` rather than via `npx`, so the exact 0.6.2 release is verified by
  its SHA-512 hash and a tampered or unpinned upstream cannot be pulled at runtime
  (npm-side parity with the hash-locked Python dependencies).
- **Mitigation (further):** Apply container egress restrictions to further bound
  what the subprocess can reach.
- **Threat 6c — unauthenticated access to privileged tools:** Same root cause as
  Spoofing (§1) — without transport auth, any caller can reach `send_mail` /
  `place_complaint_call`.
- **Status:** 🟡 **Partial.** The Terraform default already requires an
  authenticated invoker (see §1), so a caller cannot reach `send_mail` /
  `place_complaint_call` without IAM auth. Full mitigation adds per-principal
  *authorization* (not just authentication) and per-session identity binding
  before exposing the surface more broadly.

---

## Summary

| STRIDE category | Primary threat | Status |
|---|---|---|
| Spoofing | No transport authentication | 🟡 Partial (auth-invoker default) |
| Tampering | Prompt injection | ✅ Implemented (2 layers) |
| Tampering | Shared in-memory state | ⬜ Recommended |
| Repudiation | No immutable action log | 🟡 Partial |
| Information disclosure | PII to model/logs | ✅ Implemented |
| Information disclosure | Secret leakage | ✅ Implemented |
| Information disclosure | Over-sharing to counterparties | ✅ Implemented |
| Denial of service | No rate limiting | 🟡 Partial |
| Elevation of privilege | Quarantine escape | ✅ Implemented |
| Elevation of privilege | MCP subprocess over-privilege | ✅ Implemented |
| Elevation of privilege | Unauthenticated privileged tools | 🟡 Partial (auth-invoker default) |

The **runtime, agent-level** threats (injection, PII disclosure, over-sharing,
quarantine escape, MCP over-privilege) are mitigated in code, and the **Terraform
platform layer** adds authenticated access, Secret Manager, and durable BigQuery
logging. The remaining open items are **hard rate-limiting**, a dedicated
**append-only action log**, and **per-session (multi-user) state** — appropriate
to add when moving from the hackathon demo to a hosted service, and tracked in
the README roadmap.
