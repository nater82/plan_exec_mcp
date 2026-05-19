"""Healthcheck for the planner-mcp setup.

Verifies:
  1. GENAI_MIL_API_KEY is set in the environment.
  2. The genai.mil endpoint is reachable.
  3. Each model the server would actually use responds to a trivial request.

Run from the repo root:
    .venv/bin/python scripts/healthcheck.py

Exit code 0 = all green, non-zero = at least one check failed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Allow running from anywhere — find the repo root and put it on sys.path
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT))

import requests

# Import the model assignments the server would use, so this checks
# exactly what the server is configured to call (including any per-tool
# overrides from env vars).
from server import ENDPOINT, MODELS  # noqa: E402


CHECK_PROMPT = "Reply with exactly the word 'ok'."


def _check_api_key() -> tuple[bool, str]:
    key = os.environ.get("GENAI_MIL_API_KEY")
    if not key:
        return False, "GENAI_MIL_API_KEY is NOT set"
    return True, f"GENAI_MIL_API_KEY is set (length: {len(key)})"


def _check_model(model: str, timeout: float = 60.0) -> tuple[bool, str]:
    api_key = os.environ.get("GENAI_MIL_API_KEY")
    if not api_key:
        return False, "no api key (already reported)"

    t0 = time.monotonic()
    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": CHECK_PROMPT}],
                "temperature": 0,
                "max_tokens": 5,
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        return False, f"network error: {e.__class__.__name__}: {e}"

    elapsed = time.monotonic() - t0

    if resp.status_code == 200:
        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            return True, f"OK ({elapsed:.1f}s, reply: {content[:30]!r})"
        except (KeyError, IndexError, ValueError) as e:
            return False, f"200 OK but unexpected response shape ({e})"

    # Provide helpful diagnostics for common failure modes
    snippet = resp.text[:200].strip()
    if resp.status_code == 401:
        return False, f"401 unauthorized — key invalid, locked, or expired. Body: {snippet}"
    if resp.status_code == 404:
        return False, f"404 not found — model name may be wrong. Body: {snippet}"
    if resp.status_code == 429:
        return False, f"429 rate limited. Body: {snippet}"
    return False, f"HTTP {resp.status_code} ({elapsed:.1f}s): {snippet}"


def main() -> int:
    print(f"=== planner-mcp healthcheck ===")
    print(f"endpoint: {ENDPOINT}")
    print()

    all_ok = True

    # 1. API key
    ok, msg = _check_api_key()
    print(f"  [{'PASS' if ok else 'FAIL'}] api key: {msg}")
    if not ok:
        print("\nCannot check models without an API key. Set GENAI_MIL_API_KEY and re-run.")
        return 1

    # 2. Each configured model (deduplicate so we don't double-check the default)
    print()
    seen_models: dict[str, list[str]] = {}
    for tool, model in MODELS.items():
        seen_models.setdefault(model, []).append(tool)

    for model, tools in sorted(seen_models.items()):
        ok, msg = _check_model(model)
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] model {model}: {msg}")
        print(f"           used by: {', '.join(tools)}")

    print()
    if all_ok:
        print("All checks passed. The MCP server should be able to call every configured model.")
        return 0
    print("One or more checks failed. See messages above. Common fixes:")
    print("  - 401: key may be locked. Visit the unlock URL from the error body.")
    print("  - 404: the model name may have changed. Check genai.mil dashboard.")
    print("  - Network/timeout: check VPN / network policy to the genai.mil endpoint.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
