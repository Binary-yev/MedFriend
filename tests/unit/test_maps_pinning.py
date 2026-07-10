"""Regression guards for the integrity-pinned Google Maps MCP server (main branch).

These lock in the supply-chain decision for provider search: the MCP server is the
@modelcontextprotocol reference server, pinned to an exact version and installed
from a committed lockfile via `npm ci`, and it is launched out of node_modules
rather than fetched at runtime with `npx`. The tests read files directly (no ADK
import, no Node required), so they run fast in any environment, including CI.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG = "@modelcontextprotocol/server-google-maps"
PINNED_VERSION = "0.6.2"


def test_package_json_pins_exact_maps_server_version():
    pkg = json.loads((REPO_ROOT / "package.json").read_text())
    deps = pkg.get("dependencies", {})
    assert PKG in deps, f"{PKG} missing from package.json dependencies"
    # Exact pin, no range specifiers (^ ~ >= * x) so npm/npx cannot drift.
    assert deps[PKG] == PINNED_VERSION, (
        f"{PKG} must be pinned to exactly {PINNED_VERSION}, got {deps[PKG]!r}"
    )


def test_lockfile_records_integrity_hash_for_pin():
    lock_path = REPO_ROOT / "package-lock.json"
    assert lock_path.exists(), "package-lock.json must be committed so `npm ci` works"
    lock = json.loads(lock_path.read_text())
    node = lock["packages"][f"node_modules/{PKG}"]
    assert node["version"] == PINNED_VERSION
    # A SHA-512 integrity hash must be recorded so `npm ci` can verify the tarball.
    assert node.get("integrity", "").startswith("sha512-"), "missing SHA-512 integrity"


def test_agent_launches_pinned_binary_not_npx():
    src = (REPO_ROOT / "care_navigator" / "agent.py").read_text()
    # Launched from node_modules via `node`, never fetched with `npx` at runtime.
    assert 'command="node"' in src
    assert "node_modules" in src
    assert 'command="npx"' not in src


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".")[:3])


def test_sdk_override_patches_vulnerable_transitive_dep():
    """server-google-maps@0.6.2 (archived) pins @modelcontextprotocol/sdk 1.0.1,
    which carries HIGH advisories (ReDoS, DNS rebinding, cross-client data leak)
    that Trivy flags once the tree is in the image. An `overrides` block forces a
    patched SDK. Guard against the override being dropped or the lockfile going
    stale, either of which would silently reintroduce those advisories.
    """
    pkg = json.loads((REPO_ROOT / "package.json").read_text())
    override = pkg.get("overrides", {}).get("@modelcontextprotocol/sdk")
    assert override, "SDK override missing from package.json (reintroduces HIGH CVEs)"

    lock = json.loads((REPO_ROOT / "package-lock.json").read_text())
    resolved = lock["packages"]["node_modules/@modelcontextprotocol/sdk"]["version"]
    assert resolved == override, (
        f"lockfile SDK {resolved!r} != override {override!r} — run `npm install` to refresh the lockfile"
    )
    # Must be past the vulnerable range (advisories affect <= 1.25.3).
    assert _ver_tuple(resolved) >= (1, 26, 0), f"SDK {resolved} is still in the vulnerable range"
