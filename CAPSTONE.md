# Capstone requirements — how MedFriend maps to them

MedFriend was built for **Google & Kaggle's 5‑Day AI Agents Intensive**. This is the rubric‑facing companion to the [README](README.md); every claim below points to the exact file so it can be verified.

## Key concepts

The capstone asks for **at least three** key concepts. MedFriend demonstrates **five of the six in the code/repo itself** (the sixth, Antigravity, is a video item).

| Key concept | Status | Where to see it |
|-------------|:------:|-----------------|
| **Agent / multi‑agent system (ADK)** | ✅ Code | `care_navigator/agent.py` — root `Agent` (`care_navigator`) orchestrating two `LlmAgent` sub‑agents (`insurance_reviewer`, `provider_office`) via `AgentTool`; wrapped in an ADK `App` |
| **MCP server** | ✅ Code | `care_navigator/agent.py` — `maps_mcp = McpToolset(StdioServerParameters(command="node", args=[node_modules/@modelcontextprotocol/server-google-maps/dist/index.js]))`, pinned to `@0.6.2` and installed via `npm ci` |
| **Security features** | ✅ Code | **Two‑layer prompt‑injection defense** — deterministic PII scrub + signature detection (`care_navigator/security.py`, wired into `check_new_mail` and the root agent's `before_model_callback`) *plus* semantic quarantine store (`quarantine_document` + intake rules 3–4); an **LLM‑as‑a‑Judge** guardrail on the agent's output and tool calls (`plugins/agent_as_a_judge.py`); approval gates on every outbound action; data minimization; least‑privilege MCP subprocess env; **integrity‑pinned** MCP server (`@modelcontextprotocol/server-google-maps@0.6.2`, installed via `npm ci` from a committed lockfile); secrets hygiene (`.gitignore`, env‑based keys, OAuth); telemetry content suppression (`app_utils/telemetry.py`); SAST in CI (`.github/workflows/` — Bandit, CodeQL, Gitleaks, Trivy, Checkov, OSV-Scanner, Dependency Review); hash‑locked, reproducible dependencies (`uv.lock` + `uv sync --frozen`); STRIDE `threat_model.md` + `SECURITY.md`; a **STRIDE threat‑model gate** in the dev lifecycle (`.agents/` regeneration skill + `threat-model-gate.yml` CI gate that fails a PR widening the attack surface without refreshing the model + destructive‑command pre‑tool hook) |
| **Deployability** | ✅ Code/Video | `Dockerfile` (Cloud Run–ready, Node runtime + `npm ci` for the pinned MCP server), `fast_api_app.py`, `app_utils/services.py` (GCS + Gemini Enterprise Agent Platform services), `app_utils/telemetry.py` (Cloud Trace/Logging), `agents-cli deploy`, and full **Terraform IaC** in `deployment/terraform/` (Cloud Run + least‑privilege service account + Secret Manager + GCS/BigQuery, authenticated‑invoker by default) |
| **Agent skills (Agents CLI)** | ✅ Code/Video | `agents-cli-manifest.yaml`, `GEMINI.md`, and a full evaluation suite under `tests/eval/` driven by `agents-cli eval` — an **LLM‑as‑judge** quality grader (`metrics.py`) plus a deterministic **`tool_trajectory_check`** that verifies the correct tool fired (e.g. `quarantine_document` on the injection case), alongside the pytest **unit tests** in `tests/unit/` |
| **Antigravity** | 🎥 Video | `GEMINI.md` pre‑configures the project for Antigravity-assisted development; shown in the accompanying video |

## Category 2 — Implementation (70 pts)

| Rubric item | How MedFriend addresses it |
|-------------|----------------------------|
| **Technical implementation (50)** | Multi‑agent orchestration with `AgentTool`; a real MCP server over stdio (integrity‑pinned via `npm ci`); multimodal intake (text/PDF/image/audio); 13 tools including three third‑party integrations (Maps MCP, Gmail, Bland.ai); A2A interoperability; and clever, non‑obvious tool use (stateless counterparties that make multi‑turn negotiation deterministic; treating an inbound *email body* as an untrusted document). Code is heavily commented at the design level — see the block comments in `agent.py` explaining the `AgentTool` choice, the Gmail security posture, and the Bland.ai Cloudflare work‑around. |
| **Documentation (20)** | The [README](README.md) (problem, solution, architecture + diagram, setup, security), `GEMINI.md` (AI‑assisted dev guide), `tests/eval/datasets/README.md` (eval format), and thorough in‑code docstrings/comments. |
| **🚨 No secrets in code** | Verified: no keys or tokens in the working tree **or** git history. Every secret is read from an environment variable or a git‑ignored file path; `credentials.json`, `token.json`, `api_key.txt`, `*.pem`, and `*-key.json` are all in `.gitignore`. |
