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
- **Reasoning core:** the root `care_navigator` agent (Gemini 2.5 Flash) with 13
  tools, plus two `AgentTool` sub-agents (`insurance_reviewer`, `provider_office`).
- **Guardrail:** a second, isolated model call — the `LlmAsAJudge` `App` plugin
  (`gemini-2.5-flash-lite`, own runner and session) screening model responses and
  tool calls. Being a network dependency, its *availability* is part of the
  surface, not only its verdicts (threat 2c).
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
  - *Layer 3 — runtime judge (`care_navigator/plugins/agent_as_a_judge.py`):* a
    separate `gemini-2.5-flash-lite` safety agent, registered as an ADK `App`
    plugin, screens every model response in the invocation (both `AgentTool`
    sub-agents included) and every tool call before it fires, catching an
    injection that survived Layers 1–2 at the point where it would become an
    outbound action.
  - Confirmation gates mean even a *missed* injection cannot cause an autonomous
    real-world action: `send_mail` and `place_complaint_call` — the only two
    tools that act irreversibly outside the process — are wrapped in
    `FunctionTool(..., require_confirmation=True)`, so ADK suspends the call and
    the function body never executes without an out-of-band
    `{"confirmed": true}`. This holds independently of the model, which is what
    makes it a backstop rather than a third opinion.
- **Threat 2b — shared mutable state:** `CASE` (case + documents + quarantine)
  is a process-wide, in-memory dict. Concurrent users would read/overwrite each
  other's data, and all state is lost on restart.
- **Status:** ⬜ **Recommended** (accepted for the demo; see README roadmap).
- **Mitigation:** Move the case, document, and quarantine stores into per-session
  ADK state backed by a persistent, per-user datastore.
- **Threat 2c — guardrail unavailability:** The Layer-3 judge is a network call
  to a second model. If it errors or returns nothing, a naive implementation
  scores the failure as "safe" and the guardrail disappears silently while the
  system keeps advertising it.
- **Status:** ✅ **Implemented.**
- **Mitigation:** `util.run_prompt` reports failures under a distinct
  `ERROR_AUTHOR` sentinel instead of returning error text for the verdict parser
  to read, and `_evaluate` maps that to `Verdict.UNAVAILABLE` — a third state
  kept separate from `SAFE`, logged at WARNING. `before_tool_callback` fails
  **closed** on it (an unscreened real-world action does not proceed); the
  response- and user-side hooks fail **open**, trading unscreened replies for
  availability, since blocking every reply would convert a judge outage into a
  full agent outage. Fail-open on the response path is acceptable precisely
  because the two irreversible tools are gated in code (threat 2d) rather than by
  the prompt, so an unscreened reply cannot itself send mail or place a call.
  Asserted in `tests/unit/test_judge_plugin.py`.
- **Threat 2d — autonomous irreversible action:** Every other control here is a
  model judging a model. If all of them are defeated at once — a novel injection
  that survives Layers 1–2 and that the judge scores safe — the remaining
  question is whether anything non-probabilistic stands between the agent and a
  sent email or a placed phone call.
- **Status:** ✅ **Implemented** for the irreversible tools; 🟡 **Partial**
  overall.
- **Mitigation:** `send_mail` and `place_complaint_call` are wrapped in
  `FunctionTool(..., require_confirmation=True)` (`agent.py`). ADK suspends the
  call, emits an `adk_request_confirmation` request, and `FunctionTool` returns
  an error *before* invoking the function body; execution resumes only when a
  `FunctionResponse` carrying `{"confirmed": true}` arrives out-of-band, which
  the model cannot synthesize for itself. These are the only two tools with an
  external irreversible effect — `insurance_reviewer` and `provider_office` are
  bare `LlmAgent`s with no tools, so appeal submission and booking never leave
  the process, and their gates remain prompt-level by design. Asserted in
  `tests/unit/test_approval_gates.py`, including that neither sub-agent has
  acquired tools of its own. Residual risk: the confirmation must be answered by
  a human — a client that auto-confirms turns the gate into theater.

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
- **Threat 5b — denial of action via the guardrail:** Because tool calls fail
  closed when the judge returns no verdict (threat 2c), anything that reliably
  breaks the judge — exhausting its quota, or looping requests that make it time
  out — stops MedFriend from taking *any* action, without touching the root
  agent. Fail-closed converts a confidentiality/integrity risk into an
  availability one; that is the intended trade, but it is a trade.
- **Status:** 🟡 **Partial.** The failure is loud (WARNING per occurrence) and
  bounded — the agent stays able to read and answer — but nothing throttles or
  circuit-breaks the judge path itself.
- **Mitigation:** Share the rate limits above with the judge call, and add a
  short-lived circuit breaker that surfaces a single explicit "safety screening
  unavailable" state to the patient rather than failing each tool call
  individually.

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
  (npm-side parity with the hash-locked Python dependencies). CI enforces this
  rather than trusting it: `.github/workflows/ci.yml` runs `npm ci --omit=dev` on
  every push and pull request, which fails the build if `package.json` and
  `package-lock.json` ever disagree or a package's hash does not match.

  Pinning a release also pins its known vulnerabilities, so the `overrides` block
  in `package.json` carries the transitive graph forward as advisories land. It
  already forced `@modelcontextprotocol/sdk` off the vulnerable 1.0.1 that
  `server-google-maps@0.6.2` pins; it now also pins that sdk's own `hono`
  (→ 4.12.34) and `@hono/node-server` (→ 1.19.15) transitives, clearing
  CVE-2026-69207, CVE-2026-71848/71849/71850 and GHSA-frvp-7c67-39w9. Those live
  in the sdk's **HTTP** transport, which MedFriend never loads — the server is
  launched over stdio — so none were reachable here; they are patched anyway,
  because an unexploitable CVE on the dependency graph still has to be assessed
  by anyone auditing this repo, and "we looked and it does not apply" is a claim
  that decays every time the graph moves. `npm audit` reports 0 vulnerabilities.
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
- **Threat 6d — known-vulnerable OS packages in the container base layer
  (supply chain):** The image builds `FROM python:3.12-slim`. Debian publishes
  security fixes into `trixie-security`/`-updates` well before that tag is
  rebuilt against them, so the base layer routinely ships packages whose fix is
  already in the archive. Several such fixes are local-privilege-escalation bugs
  in `util-linux` — CVE-2026-53613 (TOCTOU in `mount` via an ancestor-directory
  swap) and CVE-2026-53614 (SUID `mount(8)` allowing a `nosuid`/`noexec` bypass
  via `LIBMOUNT_FORCE_MOUNT2`) — which is precisely the pillar this section
  covers: a foothold inside the container (the MCP subprocess of 6b being the
  most plausible route) could be widened toward root.
- **Status:** ✅ **Implemented.** The `Dockerfile` runs `apt-get upgrade -y`
  alongside `apt-get update` in the base layer, so the image takes published
  Debian security fixes at build time instead of waiting on an upstream
  base-image rebuild. `.github/workflows/trivy.yml` enforces this independently:
  it builds the image on every push, every pull request, and weekly, and fails
  the job (`exit-code: 1`) on any HIGH/CRITICAL OS or library finding, with
  `ignore-unfixed: true` scoping the gate to vulnerabilities that actually have
  a fix available.
- **Mitigation (further):** `apt-get upgrade` holds back any upgrade that would
  require installing or removing a package; `dist-upgrade` is the escalation if
  a future fix is ever silently held back that way.

- **Threat 6e — over-broad runtime service account:** Cloud Run runs the agent
  under a service account (`service.tf`). Anything that gets code execution in
  that container — the MCP subprocess of 6b, a dependency compromise — inherits
  every role that account holds. Two of the original grants were project-wide
  when the app only ever touches specific resources: `roles/storage.admin` (full
  control of *every* bucket in the project, including creating, deleting, and
  rewriting bucket IAM) and a project-level `roles/secretmanager.secretAccessor`
  (read access to every secret in the project, including ones added later by
  anyone).
- **Status:** ✅ **Implemented** for the runtime identity; 🟡 **Partial**
  overall.
- **Mitigation:** Both are now resource-scoped. `storage.admin` is replaced by
  `roles/storage.objectAdmin` bound to the logs bucket alone
  (`google_storage_bucket_iam_member` in `storage.tf`) — sufficient because
  Terraform creates the bucket and `GcsArtifactService` only ever calls
  upload/get/list/delete on blobs inside it. The project-level secret accessor is
  replaced by three `google_secret_manager_secret_iam_member` bindings, one per
  secret the container actually mounts. What remains project-wide is
  `roles/aiplatform.user` (no narrower predefined role exists for calling a
  model) plus `logging.logWriter`, `cloudtrace.agent` and
  `serviceusage.serviceUsageConsumer`, which are already minimal.
- **Residual risk:** the **deploy-time** identity is not hardened. `iam.tf`
  grants `roles/cloudbuild.builds.builder` to the *default compute* service
  account so `gcloud run deploy --source` can build and push. That is a shared
  identity holding the broadest role in the file. Narrowing it means moving
  builds to a dedicated build service account, which depends on the deployment
  pipeline; recorded here rather than silently left out.

---

## Summary

| STRIDE category | Primary threat | Status |
|---|---|---|
| Spoofing | No transport authentication | 🟡 Partial (auth-invoker default) |
| Tampering | Prompt injection | ✅ Implemented (3 layers) |
| Tampering | Guardrail unavailability | ✅ Implemented (fail-closed on tools) |
| Tampering | Autonomous irreversible action | ✅ Implemented (code-enforced confirmation) |
| Tampering | Shared in-memory state | ⬜ Recommended |
| Repudiation | No immutable action log | 🟡 Partial |
| Information disclosure | PII to model/logs | ✅ Implemented |
| Information disclosure | Secret leakage | ✅ Implemented |
| Information disclosure | Over-sharing to counterparties | ✅ Implemented |
| Denial of service | No rate limiting | 🟡 Partial |
| Denial of service | Denial of action via the guardrail | 🟡 Partial |
| Elevation of privilege | Quarantine escape | ✅ Implemented |
| Elevation of privilege | MCP subprocess over-privilege | ✅ Implemented |
| Elevation of privilege | Vulnerable OS packages in base image | ✅ Implemented |
| Elevation of privilege | Over-broad runtime service account | ✅ Implemented (resource-scoped) |
| Elevation of privilege | Unauthenticated privileged tools | 🟡 Partial (auth-invoker default) |

The **runtime, agent-level** threats (injection, PII disclosure, over-sharing,
quarantine escape, MCP over-privilege, guardrail unavailability) are mitigated in
code, and the **Terraform platform layer** adds authenticated access, Secret
Manager, and durable BigQuery logging. The remaining open items are **hard
rate-limiting** (including a circuit breaker on the guardrail path), a dedicated
**append-only action log**, and **per-session (multi-user) state** — appropriate
to add when moving from the hackathon demo to a hosted service, and tracked in
the README roadmap.

---

## Keeping this assessment current (governance)

This document is a maintained assessment, not a write-once artifact. A
development-lifecycle gate (defined in `.agents/CONTEXT.md`) keeps it honest:

- **Regeneration skill** — `.agents/skills/stride-threat-model/` walks the
  codebase across all six pillars and refreshes the sections above, preserving
  the ✅/🟡/⬜ status convention and requiring each status to cite real code.
- **CI gate** — `.github/workflows/threat-model-gate.yml` fails any pull request
  that changes an attack-surface file — the application surface
  (`care_navigator/agent.py`, `fast_api_app.py`, `security.py`, `plugins/`,
  `app_utils/`) or the deployment surface (`deployment/terraform/`, `Dockerfile`,
  `package.json`/`package-lock.json`, `authorize_gmail.py`) — without updating this file in
  the same PR, so the assessment cannot silently drift from the code. (A change
  that touches those files but genuinely does not alter the surface can bypass the
  gate with the `threat-model-not-needed` PR label.)
- **TDD Planning Gate** — every feature plan must include a *Security Boundaries &
  Assertions* section mapping the feature's abuse vectors to the pillars above
  before any code is written.
- **Destructive-command hook** — a supporting development-time control
  (`.agents/hooks.json` → `.agents/scripts/validate_tool_call.py`) blocks
  destructive shell commands from the coding agent; it protects the developer
  environment, distinct from the runtime, patient-facing threats analyzed above.

Note that the CI gate proves this document was *updated* alongside a surface
change; it does not prove the analysis is *correct* — that remains the job of code
review and the regeneration skill.
