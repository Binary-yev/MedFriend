import os

import pytest
from dotenv import load_dotenv

# Load .env file before any tests or imports run
load_dotenv()


def _have_real_key() -> bool:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key) and key.lower() != "dummy"


def pytest_collection_modifyitems(config, items):
    """Gate tests marked `live`.

    Live tests make real Gemini calls. They run only when RUN_LIVE_TESTS=1 AND a
    real GEMINI_API_KEY is present, so:
      * local runs without a key -> skipped
      * CI on owner pushes (secret present) -> run
      * CI on fork PRs (GitHub withholds secrets) -> skipped, not failed
    """
    if os.getenv("RUN_LIVE_TESTS") == "1" and _have_real_key():
        return
    if os.getenv("RUN_LIVE_TESTS") == "1" and not _have_real_key():
        reason = "live test requested but no real GEMINI_API_KEY is available"
    else:
        reason = "live test; set RUN_LIVE_TESTS=1 with a real GEMINI_API_KEY to run"
    skip_live = pytest.mark.skip(reason=reason)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
