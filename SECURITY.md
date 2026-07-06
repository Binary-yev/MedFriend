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
  security layer `care_navigator/security.py`).
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

- **Prompt-injection defense, two layers.**
  - *Layer 1 — deterministic (`care_navigator/security.py`):* regex/keyword
    screening that redacts high-risk PII (SSNs, payment cards) and flags known
    injection signatures **in code, before untrusted text reaches the model**.
    Wired into the email channel (`check_new_mail`) and the pasted-text channel
    (the root agent's `before_model_callback`).
  - *Layer 2 — semantic (the agent's instruction + quarantine store):* the model
    classifies each document CLEAN vs TAMPERED and routes tampered content to a
    quarantine / dead-letter store that is invisible to downstream reasoning.
- **Human approval gates** on every real-world action (submitting an appeal,
  sending email, placing a call, booking).
- **Data minimization** — only the minimum data goes to each counterparty (e.g.
  location + specialty to the Maps search, never patient identity or health
  details).
- **Secrets hygiene** — no keys or tokens are committed; secrets come from
  environment variables or git-ignored file paths; Gmail uses the patient's own
  OAuth token.
- **Telemetry content suppression** — prompt/response content is kept out of
  trace spans (`care_navigator/app_utils/telemetry.py`).
- **Static analysis in CI** — Bandit, CodeQL (security-extended), and Dependency
  Review run on every push/PR and weekly (`.github/workflows/security.yml`).

## Known limitations

- The demo case, document store, and quarantine live in module-level in-memory
  state; production would move these into per-session state with a persistent,
  auditable store (see the README roadmap).
- The FastAPI surface does not itself enforce authentication; deploy it behind an
  authenticating gateway (e.g. Cloud Run IAM / IAP) before exposing it.
- The deterministic pre-filter is high-precision, not exhaustive — it is a
  defense-in-depth layer in front of the model's judgment, not a replacement for
  it.
