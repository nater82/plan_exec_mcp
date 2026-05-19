"""Run the v4 planner prompt against all sample reports and score.

For each report:
  - Send to gemini-3.1-pro-preview via genai.mil
  - Parse JSON (with fence-tolerant fallback)
  - Score: valid JSON?, step count, which tools used, latency, tokens

Print a summary table and full plans for manual review.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# Allow `from planner_prompt` (at repo root) and `from sample_reports` (in tests/).
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))             # tests/ — for sample_reports
sys.path.insert(0, str(_HERE.parent))      # repo root — for planner_prompt

from planner_prompt import build_messages  # noqa: E402
from sample_reports import ALL_REPORTS  # noqa: E402

ENDPOINT = "https://api.genai.mil/v1/chat/completions"
MODEL = "gemini-3.1-pro-preview"

EXPECTED_TOOLS = {"read_file", "grep_files", "web_fetch", "post_alert", "draft_report"}


def extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass
    return None


def call_planner(api_key: str, report_text: str) -> tuple[dict | None, dict]:
    payload = {
        "model": MODEL,
        "messages": build_messages(
            user_intent="produce a safety officer notification",
            input_text=report_text,
        ),
        "temperature": 0.1,
    }
    t0 = time.monotonic()
    resp = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    elapsed = time.monotonic() - t0

    meta = {"http_status": resp.status_code, "elapsed_s": elapsed}
    if resp.status_code != 200:
        meta["error"] = resp.text[:500]
        return None, meta

    body = resp.json()
    usage = body.get("usage", {})
    meta["prompt_tokens"] = usage.get("prompt_tokens")
    meta["completion_tokens"] = usage.get("completion_tokens")

    content = body["choices"][0]["message"]["content"]
    meta["clean_json"] = content.strip().startswith("{") and content.strip().endswith("}")

    plan = extract_json(content)
    if plan is None:
        meta["raw_content"] = content[:500]
    return plan, meta


def score_plan(plan: dict | None) -> dict:
    if plan is None:
        return {"valid": False, "step_count": 0, "tools_used": set(), "severity": None, "human_review": None}
    steps = plan.get("steps", [])
    tools_used = {s.get("tool") for s in steps if isinstance(s, dict) and s.get("tool")}
    return {
        "valid": True,
        "step_count": len(steps),
        "tools_used": tools_used,
        "severity": plan.get("severity"),
        "human_review": plan.get("human_review_required"),
    }


def main() -> int:
    api_key = os.environ.get("GENAI_MIL_API_KEY")
    if not api_key:
        print("GENAI_MIL_API_KEY not set", file=sys.stderr)
        return 1

    results = []
    for name, report in ALL_REPORTS.items():
        print(f"\n{'='*70}\n=== {name} ===\n{'='*70}")
        plan, meta = call_planner(api_key, report)
        scored = score_plan(plan)

        print(f"HTTP {meta['http_status']}  ({meta['elapsed_s']:.1f}s, "
              f"in={meta.get('prompt_tokens')} out={meta.get('completion_tokens')})")
        print(f"Valid JSON: {scored['valid']}  clean: {meta.get('clean_json')}")
        print(f"Severity: {scored['severity']}  human_review: {scored['human_review']}  "
              f"steps: {scored['step_count']}")
        print(f"Tools used: {sorted(scored['tools_used'])}")
        print(f"Tools NOT used: {sorted(EXPECTED_TOOLS - scored['tools_used'])}")

        if plan:
            print("\n--- PLAN ---")
            print(json.dumps(plan, indent=2))
        else:
            print(f"\n--- RAW (truncated) ---\n{meta.get('raw_content', meta.get('error', ''))}")

        results.append((name, scored, meta))

    print(f"\n{'='*70}\n=== SUMMARY ===\n{'='*70}")
    print(f"{'report':<22} {'valid':<6} {'steps':<6} {'sev':<10} {'review':<7} {'time(s)':<8} {'tools_used'}")
    for name, scored, meta in results:
        print(f"{name:<22} {str(scored['valid']):<6} {scored['step_count']:<6} "
              f"{str(scored['severity']):<10} {str(scored['human_review']):<7} "
              f"{meta['elapsed_s']:<8.1f} {sorted(scored['tools_used'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
