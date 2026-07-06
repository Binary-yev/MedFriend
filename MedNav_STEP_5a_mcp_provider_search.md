# MedNav — Step 5a: MCP Connection + Live Provider Search
### For Antigravity to wire. Connection + search ONLY — no booking (that's Step 5b).

**Prerequisite:** Steps 1–4 committed and passing (`TESTS.md` green). The agent is a single `agent.py` with in-process function tools, run in `adk web`.

---

## Goal (scope this tightly)

Connect the agent to the **Google Maps MCP server** via ADK's `MCPToolset`, and prove it returns **real** nearby orthopedic providers for a ZIP code. The patient then **selects** one from the list. **Stop there.** No booking, no contacting the office, no scheduling — those are Step 5b.

This is the checkpoint that isolates the "is MCP connected?" question from the booking logic that comes next. **Commit as soon as the DoD passes, before any booking work.**

---

## What to build

1. **Connect an `MCPToolset` to the Google Maps MCP server** and add it to the agent's `tools` list **alongside** the existing function tools (do not replace them).
2. **Add a provider-search behavior** driven by the Maps MCP's tools: given a ZIP, find real orthopedic providers nearby (geocode the ZIP if the server requires it, then a nearby/text place search for "orthopedic surgeon").
3. **Add this instruction rule** (rule 6) to the agent's `INSTRUCTION`:

   > **6) FIND A PROVIDER (live search via the Google Maps MCP)** — when the patient wants to find a doctor/provider:
   > - Ask for their ZIP code (and confirm the specialty — orthopedic surgeon for the hip replacement) if not given.
   > - Use the Google Maps MCP tools to find real orthopedic providers near that ZIP (geocode the ZIP if needed, then search nearby).
   > - Present a short **numbered list** of what you found: name, address, and rating if available. Frame it as "here's what I found near you."
   > - You CANNOT confirm insurance network status — tell the patient to **verify in-network with their plan**.
   > - Ask the patient to **SELECT one** from the list. Then STOP. Do NOT book anything — booking is a later step.
   > - Send only the location and specialty to the search — never patient identity or health details.

---

## Do NOT touch

- The existing tools and their behavior: `get_insurance_profile`, `get_benefits`, `contact_party`, `save_document`, `quarantine_document`, `list_quarantine`, `discard_quarantine`, `list_documents`.
- The existing instruction rules 1–5 (plan facts, contact-a-party, document intake, quarantine lifecycle, appeal flow). Do not refactor them.

## Do NOT add yet (Step 5b)

The booking flow · asking for preferred times · contacting the office · the scheduling interrupt · any calendar.

---

## Technical notes (these are environment-specific — figure them out against the installed setup)

- **Use the CURRENT ADK MCP API** for the installed ADK version — check the installed ADK's MCP tool module for the exact `MCPToolset` class and connection parameters. Do NOT assume an import path or an older `from_server()` pattern from memory; verify against the actual installed version.
- **Server choice:** prefer the **official Google-maintained Google Maps MCP server**; a community Google Maps MCP server (e.g. an `npx` stdio one) is a fallback. Whichever one connects — build the search behavior around the **geocode + place-search tools it actually exposes** (tool names differ between servers, so inspect what the connected server provides).
- **Connection method:** stdio (launch the MCP server as a local subprocess) or HTTP/SSE (a running server URL) — use whatever the chosen server supports and gets a clean connection.
- **API key handling:** pass the Google Maps API key to the **MCP server** (via env, e.g. `GOOGLE_MAPS_API_KEY`), NOT to the agent, and NEVER hardcode it. Keep it gitignored.

## Prerequisites / gotchas (check these first if search fails)

- **Places API (New) must be enabled** on the GCP project (having "a Maps API key" does not guarantee Places specifically is on). If a search returns an "API not enabled" error, enable Places API (New) in the console.
- **Billing** must be enabled on the project (likely already is).
- The API key must be reachable by the MCP server at runtime.

---

## Definition of Done

1. On `adk web` startup, the agent **connects to the Maps MCP server** and its tools load (no connection error).
2. "Find me an orthopedic surgeon near **[a real ZIP]**" → the agent returns **real providers** (real names/addresses) obtained via the MCP tools, as a numbered list, with the "verify in-network with your plan" note.
3. The patient can **select** one; the agent acknowledges the selection and **stops** (no booking attempted).
4. The Maps API key is **not hardcoded** anywhere (env/secret, gitignored).
5. **No regressions** — re-run `TESTS.md`; Steps 1–4 behavior is unchanged.

---

## If it fails — where to look (connection, not logic)

The agent's provider-search *behavior* is trivial; the work here is the **connection**. So if no providers come back or it errors, debug in this order — all connection issues, not instruction issues:
1. Is the MCP server actually running / reachable?
2. Is the API key being passed to the **server** (not the agent)?
3. Is **Places API (New)** enabled + billing on the project?
4. Is the `MCPToolset` connected — do the server's tools show up in the agent's tool list / trace?

Do NOT rewrite the instruction to "fix" a connection problem. When the DoD passes, commit — then Step 5b (the booking flow + scheduling interrupt) goes on top.
