# Security Policy

MedFriend is a care-navigation agent that reads a patient's documents and, on
approval, sends email and places phone calls on their behalf. Because it acts in
the world with access to personal information, security is a first-class concern.

## Supported versions

| Version | Supported |
|---------|-----------|
| `main`  | ✅ Active development |
| Others  | ❌ Not supported |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a vulnerability, report it responsibly:

1. **GitHub Private Security Advisory (preferred):** open the repository's
   **Security** tab and click **"Report a vulnerability."**
2. **Email:** contact the maintainer directly (see the contributor profile).

Please include a description and impact, steps to reproduce, and any suggested
mitigation. We aim to acknowledge reports within **48 hours** and to provide a
fix timeline within **7 days** for critical issues.

## Scope

In scope:
- The agent and its tools in `care_navigator/` (including the deterministic
  security layer `care_navigator/security.py` and the runtime guardrail plugins
  in `care_navigator/plugins/`).
- The FastAPI serving surface `care_navigator/fast_api_app.py` and the A2A
  routes in `care_navigator/app_utils/`.
- The evaluation pipeline in `tests/eval/`.

Out of scope:
- Third-party dependencies (report those upstream).
- The Google ADK framework itself (report to
  [google/adk-python](https://github.com/google/adk-python)).
- The simulated counterparties and fictional demo data (BluePeak plan, member
  ID, clinical notes) — these are illustrative, not real systems.

## How MedFriend defends itself

MedFriend's security design is documented in detail in the README
([Security & safety](README.md#security--safety)) and in the STRIDE
[`threat_model.md`](threat_model.md). In summary:

- **Prompt-injection defense, three layers.**
  - *Layer 1 — deterministic (`care_navigator/security.py`):* regex/keyword
    screening that redacts high-risk PII (SSNs, payment cards) and flags known
    injection signatures **in code, before untrusted text reaches the model**.
    Wired into the email channel (`check_new_mail`) and the pasted-text channel
    (the root agent's `before_model_callback`).
  - *Layer 2 — semantic (the agent's instruction + quarantine store):* the model
    classifies each document CLEAN vs TAMPERED and routes tampered content to a
    quarantine / dead-letter store that is invisible to downstream reasoning.
  - *Layer 3 — runtime judge (`care_navigator/plugins/agent_as_a_judge.py`):* a
    separate `gemini-2.5-flash-lite` safety agent, registered as an ADK `App`
    plugin, screens **every model response in the invocation** (sub-agents
    included) and **every tool call before it fires**, blocking what its
    jailbreak rubric (`plugins/prompts.py`) flags. It does not screen the user's
    own message — that is what Layers 1–2 are for, and blocking there would
    preempt the intended quarantine response.
- **Explicit guardrail failure policy.** A screening run that reaches no verdict
  (the judge errored or returned nothing) is recorded as `Verdict.UNAVAILABLE`
  and logged — it is never counted as "safe". Tool calls then fail **closed**, so
  an unscreened real-world action does not proceed; responses fail **open**, so a
  judge outage degrades MedFriend to a read-only assistant rather than taking it
  offline entirely.
- **Human approval gates** on every real-world action (submitting an appeal,
  sending email, placing a call, booking). For the two tools with an
  irreversible external side effect — `send_mail` (a real Gmail send) and
  `place_complaint_call` (a real outbound phone call) — the gate is enforced in
  **code**, not in the prompt: both are wrapped in ADK's
  `FunctionTool(..., require_confirmation=True)`, so the function body cannot
  run until a `FunctionResponse` carrying `{"confirmed": true}` comes back
  out-of-band. The remaining gates (appeal submission, booking) are prompt-level,
  because those paths reach simulated counterparties — `insurance_reviewer` and
  `provider_office` are bare `LlmAgent`s with no tools, so nothing leaves the
  process.
- **Data minimization** — only the minimum data goes to each counterparty (e.g.
  location + specialty to the Maps search, never patient identity or health
  details).
- **Secrets hygiene** — no keys or tokens are committed; secrets come from
  environment variables or git-ignored file paths; Gmail uses the patient's own
  OAuth token.
- **Telemetry content suppression** — prompt/response content is kept out of
  trace spans (`care_navigator/app_utils/telemetry.py`).
- **Static analysis in CI** — Bandit, CodeQL (security-extended), and Dependency
  Review run on every push/PR and weekly, alongside Gitleaks, Trivy, Checkov, and
  OSV-Scanner (see `.github/workflows/`).
- **STRIDE threat-model gate** — the assessment in `threat_model.md` is kept in
  sync with the code by a development-lifecycle gate (`.agents/CONTEXT.md`): a
  reusable `stride-threat-model` skill regenerates it, a CI workflow
  (`.github/workflows/threat-model-gate.yml`) fails any PR that changes an
  attack-surface file without updating `threat_model.md`, and a pre-tool hook
  (`.agents/hooks.json`) blocks destructive shell commands from the coding agent.

## Known limitations

- The demo case, document store, and quarantine live in module-level in-memory
  state; production would move these into per-session state with a persistent,
  auditable store (see the README roadmap).
- The FastAPI application does not itself authenticate callers; it relies on the
  platform. The provided Terraform defaults the Cloud Run service to requiring an
  **authenticated invoker** (Cloud Run IAM) with the public `allUsers` binding
  commented out — front it with IAP / a gateway for stricter control, and bind
  each session to the authenticated principal before serving multiple users.
- The deterministic pre-filter is high-precision, not exhaustive — it is a
  defense-in-depth layer in front of the model's judgment, not a replacement for
  it.
- The Layer-3 judge is itself a model, so it is probabilistic: it can miss a
  novel jailbreak, and on the response path it fails **open** by design, meaning
  a judge outage lets replies through unscreened (tool calls still fail closed).
  Neither the judge nor the pre-filter is a substitute for the confirmation
  gates on `send_mail` and `place_complaint_call`, which are enforced in code and
  hold regardless of what any model concludes. The prompt-level gates on the
  simulated counterparty paths carry no such guarantee — they are
  instruction-following, and a model that has been argued out of them will not be
  stopped by them.
- Under SSE streaming (`streaming=true` on `/run_sse`) the response-side screen
  runs per partial chunk rather than over the assembled reply, so an early chunk
  can reach the client before a later one is judged. The default non-streaming
  path screens the response as a whole.
