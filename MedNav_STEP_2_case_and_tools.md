# MedNav — Step 2: The Other Party (3-way) + Case Data
### Goal: a second LLM (insurance / hospital office) that talks back — so it's three-way from here on.

**Prerequisite:** Step 1 works (chat + menu).

---

## Build exactly this

**A) Case data + two simple tools** (synthetic, in-memory):
- A `CASE` dict: name, `procedure = "hip replacement"`, and an `insurance` profile (carrier, plan, member id, deductible, out-of-pocket).
- `get_insurance_profile()` and `get_benefits(category)` function tools (clear docstrings).

**B) The OTHER PARTY — the key part:**
- A `contact_party(party: str, message: str) -> str` tool. Inside, it calls a **second Gemini** with a **persona** for that party and returns the reply text.
- Two personas:
  - `"insurance"` — a BluePeak prior-authorization reviewer: cautious, asks for documentation; **denies** an initial surgery request citing "no cardiac clearance on file"; **approves** an appeal that addresses the cardiac clearance.
  - `"provider_office"` — a hip surgeon's scheduling office: friendly; **offers 2–3 appointment date options**.
- Your agent's instruction: when it needs a decision or info from insurance or the office, **call `contact_party` and relay the other party's reply to the patient (quote it), then propose the next step.**

## Do NOT add yet

The full appeal flow · the scheduling flow · documents · live search · UI · cloud.

## Done when

- You pick a step and ask your agent to contact a party — e.g. "ask my insurance if the surgery is covered" → your agent calls `contact_party("insurance", ...)` → **the insurance LLM replies** (a denial) → your agent **shows you that reply** and suggests a next step.
- You can see the three-way in the chat: **you → your agent → the insurance agent → back to you.**

## Hint (the other party is a real second LLM)

```python
import os
from google import genai

def contact_party(party: str, message: str) -> str:
    """Send a message to an outside party ('insurance' or 'provider_office') and return their reply."""
    personas = {
        "insurance": "You are a BluePeak insurance prior-auth reviewer. Be cautious and cite plan rules. "
                     "Deny an initial surgery authorization for lack of a pre-op cardiac clearance (stroke history). "
                     "Approve an appeal that documents/addresses the cardiac clearance. Reply as a short official message.",
        "provider_office": "You are the scheduling office for an orthopedic surgeon. Be friendly and offer 2-3 "
                           "specific appointment date options. Reply as a short message.",
    }
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{personas[party]}\n\nIncoming message from the patient's care navigator:\n{message}",
    )
    return r.text

# Agent(..., tools=[get_insurance_profile, get_benefits, contact_party])
```
*(This is the simplest reliable way to get a real 3-way. It can become a full ADK sub-agent later; not needed now.)*
