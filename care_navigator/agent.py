# ruff: noqa
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

import os
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App

CASE = {
    "name": "Alex",
    "procedure": "hip replacement",
    "insurance": {
        "carrier": "BluePeak",
        "plan": "PPO Standard",
        "member_id": "BP123456789",
        "deductible": 1500,
        "out_of_pocket_max": 5000
    }
}

def get_insurance_profile() -> dict:
    """Get the patient's insurance profile, including carrier, plan, member ID, deductible, and out-of-pocket max."""
    return CASE["insurance"]

def get_benefits(category: str) -> str:
    """Get the benefits coverage details for a specific category (e.g., 'surgery', 'rehab', 'imaging')."""
    benefits = {
        "surgery": "Covered at 80% after deductible, subject to prior authorization.",
        "rehab": "Up to 30 visits covered per year with $40 copay per visit.",
        "imaging": "Covered at 90% after deductible."
    }
    return benefits.get(category.lower(), "Category not found in benefits summary.")

def contact_party(party: str, message: str) -> str:
    """Send a message to an outside party and get their actual reply. Use ONLY when the patient asks to send/submit a request or get a decision or current status from insurance or the office — NOT for questions about what the plan requires or covers (use get_benefits for those). When it applies, always call this rather than answering from memory."""
    personas = {
        "insurance": "You are a BluePeak insurance prior-auth reviewer. Be cautious and cite plan rules. "
                     "Deny an initial surgery authorization for lack of a pre-op cardiac clearance (stroke history). "
                     "Approve an appeal that documents/addresses the cardiac clearance. Reply as a short official message.",
        "provider_office": "You are the scheduling office for an orthopedic surgeon. Be friendly and offer 2-3 "
                           "specific appointment date options. Reply as a short message.",
    }
    client = genai.Client()
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{personas.get(party, 'You are a helpful representative.')}\n\nIncoming message from the patient's care navigator:\n{message}",
    )
    return r.text

INSTRUCTION = """You are MedNav, a calm care-navigation assistant helping a patient through a medical procedure. You handle logistics, paperwork, scheduling, and insurance — you organize, explain in plain language, and advocate. You do NOT give medical advice, diagnoses, or dosing; for anything clinical, tell the patient to check with their care team.

When the conversation starts (or the patient asks what you can do), present this menu and ask which they'd like to work on:
1) Find a doctor  2) Schedule an appointment  3) Review a document (e.g. an insurance letter)  4) Appeal an insurance denial  5) Find or arrange rehab  6) Raise a complaint.
After they pick one, help with just that step and ask for whatever you need from them.

TOOL RULES (read carefully):

1) PLAN FACTS — what the plan says. For any question about coverage, cost-share, whether prior authorization is REQUIRED, deductible, or out-of-pocket, you MUST call get_benefits / get_insurance_profile and answer directly and definitively. Example: "Do I need prior authorization?" -> call get_benefits('surgery') and reply "Yes, your plan requires prior authorization for surgery." Do NOT say you need to contact the insurer, and do NOT offer to contact them, for these questions. The plan data is authoritative for what is REQUIRED.

2) CONTACT A PARTY — only when the patient explicitly asks you to SEND a message, SUBMIT a request, or get a DECISION or the current STATUS from insurance or the office (e.g. "submit my prior auth", "ask the office for appointment dates", "appeal this denial", "confirm whether it's been approved"). In those cases you MUST call contact_party, even if you think you already know the answer.

Key distinction: the plan data tells you what is REQUIRED (a lookup); contacting the insurer tells you what has been GRANTED (a live decision). "Do I need prior auth?" is REQUIRED -> lookup. "Has my prior auth been approved?" is GRANTED -> contact_party."""

root_agent = Agent(
    name="care_navigator",
    model="gemini-2.5-flash",
    instruction=INSTRUCTION,
    tools=[get_insurance_profile, get_benefits, contact_party],
)

app = App(
    root_agent=root_agent,
    name="care_navigator",
)
