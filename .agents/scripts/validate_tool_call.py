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

"""Pre-tool hook: intercept and block destructive shell executions.

Wired via `.agents/hooks.json` as a PreToolUse hook on `run_command`. The agent
platform pipes the pending command to this script's stdin BEFORE running it; a
non-zero exit blocks the call. This is a deterministic, code-level guardrail — it
does not rely on the model's judgment — matching MedFriend's defense-in-depth
philosophy (see `care_navigator/security.py` and `threat_model.md`, Elevation of
Privilege).

The block-list targets unambiguously destructive filesystem/format commands. It
is intentionally high-precision (few false positives): benign commands the agent
legitimately needs are left alone.
"""

from __future__ import annotations

import json
import re
import sys

# Unambiguously destructive command patterns. Matched case-insensitively against
# a whitespace-normalized form of the command, so `rm  -rf   /` still trips.
BLOCKED_PATTERNS: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf ~",
    "rm -rf *",
    "rm -fr /",
    "rm -f /",
    "rmdir /s",
    "del /f /s /q",
    "format c:",
    "mkfs",
    "dd if=",
    "> /dev/sda",
    ":(){ :|:& };:",  # classic fork bomb
    "git push --force",
    "git reset --hard origin",
)


def _extract_command(raw_input: str) -> str:
    """Pull the command string out of stdin, tolerating JSON or plain text."""
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError:
        return raw_input
    if isinstance(data, dict):
        # Accept the common keys different platforms use for the command payload.
        for key in ("CommandLine", "command", "cmd", "args"):
            val = data.get(key)
            if val:
                return val if isinstance(val, str) else " ".join(map(str, val))
    return raw_input


def main() -> None:
    raw_input = sys.stdin.read().strip()
    if not raw_input:
        # Nothing to validate — allow.
        sys.exit(0)

    command_str = _extract_command(raw_input)
    # Normalize runs of whitespace to single spaces so spacing tricks don't evade.
    normalized = re.sub(r"\s+", " ", str(command_str).strip().lower())

    for pattern in BLOCKED_PATTERNS:
        if pattern in normalized:
            print(
                f"[BLOCKED] Refused destructive shell command: {command_str!r} "
                f"(matched safety rule {pattern!r}). If this was intentional, run "
                f"it manually outside the agent.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Command is safe.
    sys.exit(0)


if __name__ == "__main__":
    main()
