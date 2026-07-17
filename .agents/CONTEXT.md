# Local Project Context & Secure Coding Standards

This file defines MedFriend's secure-by-default development rules and the gates a
coding agent must pass. It complements `GEMINI.md` (the general coding-agent
guide) and the STRIDE assessment in [`threat_model.md`](../threat_model.md).

## Core Paved Roads
We address common vulnerability classes by reusing MedFriend's existing
secure-by-default patterns instead of writing raw logic from scratch.

1. **Untrusted input goes through the pre-filter.** Any new channel that ingests
   attacker-controllable content (text, PDF, image, audio, email) MUST route it
   through the deterministic Layer-1 screen (`care_navigator/security.py` →
   `screen_text`) before the model reasons over it, exactly as `check_new_mail`
   (`_apply_security_prefilter`) and the root agent's `before_model_callback`
   (`security_prefilter_callback`) already do. Never feed raw untrusted text to
   the model or to a log sink.
2. **Tampered content is quarantined, never trusted.** Suspicious/injected
   documents go to the dead-letter store via `quarantine_document`; they are
   never saved with `save_document`, never acted on, and released only by
   re-ingesting a fresh clean copy (see DOCUMENT INTAKE + QUARANTINE LIFECYCLE in
   the agent `INSTRUCTION`).
3. **Real-world actions are approval-gated.** Any tool that emails, calls, or
   otherwise acts outside the process (`send_mail`, `place_complaint_call`,
   appeal/booking/complaint submission) must require explicit patient approval
   first — no autonomous outbound action.
4. **Least privilege for subprocesses.** A subprocess (e.g. the Maps MCP server)
   receives only the environment it needs (`_scoped_maps_env` strips MedFriend's
   secrets and passes only `GOOGLE_MAPS_API_KEY`) and runs from an
   integrity-locked lockfile, never an unpinned network fetch.
5. **No secrets in source.** Secrets load from env / git-ignored paths (and
   Secret Manager in deployment). `detect-secrets` + `detect-private-key`
   pre-commit hooks are the commit-time backstop; if one fails, treat it as a
   task to remediate — do not bypass it.
6. **No destructive shell.** A PreToolUse hook (`.agents/hooks.json` →
   `.agents/scripts/validate_tool_call.py`) deterministically blocks unambiguously
   destructive commands (`rm -rf /`, `git push --force`, `mkfs`, fork bombs, …)
   before they run. If you genuinely need such an action, run it manually outside
   the agent — do not weaken the block-list to get past it.

## STRIDE Threat-Model Gate
`threat_model.md` is a maintained STRIDE assessment, not a one-time document.
Whenever you add or change an entry point, tool, external integration, or data
store, you MUST refresh it by running the **`stride-threat-model`** skill
(`.agents/skills/stride-threat-model/`) and updating the affected pillar's status
marker (✅ Implemented / 🟡 Partial / ⬜ Recommended) with a citation to the code
that justifies it. A pull request that widens the attack surface without a
corresponding `threat_model.md` update does not pass this gate.

This gate is enforced in CI by
[`.github/workflows/threat-model-gate.yml`](../.github/workflows/threat-model-gate.yml):
a PR that touches a watched surface file (`care_navigator/agent.py`,
`fast_api_app.py`, `security.py`, or `plugins/`) without updating
`threat_model.md` fails the build. For a change that touches a watched file but
genuinely does not alter the attack surface (e.g. a comment or logging tweak),
add the `threat-model-not-needed` label to the PR to pass deliberately.

## TDD Planning Gate
During the Plan phase, decompose the task into logical, modular stages. Every
implementation plan MUST include a dedicated **Security Boundaries & Assertions**
section that, before a single line of code is written, maps the feature's abuse
vectors to the STRIDE pillars above and names the specific control (a Paved Road
pattern, an approval gate, a pre-filter, a scoped env, an audit record) that
mitigates each one. If the feature adds an untrusted-input channel or an outbound
action, the plan must also state which tests will prove the control holds.
