"""Test gemini-3.1-pro-preview as a planner via genai.mil.

Sends a fictional training-incident report and asks for a structured
triage plan. Designed to evaluate whether Gemini Pro can produce
plans prescriptive enough to hand to a weaker executor model.
"""

import json
import os
import sys
import time

import requests

ENDPOINT = "https://api.genai.mil/v1/chat/completions"
MODEL = "gemini-3.1-pro-preview"

PLANNER_SYSTEM = """You are a triage planner for command post incident reports during military training operations. You produce structured plans that a separate executor agent (a less-capable model with tool calling) will follow step by step.

Your job is NOT to investigate — it is to plan the investigation. Output a JSON plan with discrete steps. Each step must specify exactly which tool to call and what arguments to pass. The executor cannot make judgment calls; it just runs the steps you give it.

Available executor tools:
- web_fetch(url: str) -> str — fetch URL contents (weather, public references, etc.)
- read_file(path: str) -> str — read a local file from /reports/ or /references/
- grep_files(pattern: str, path: str) -> list[str] — search files for a regex pattern
- post_alert(channel: str, severity: str, message: str) -> str — post to Slack/Teams; severity in [info, warning, urgent]
- draft_report(template: str, fields: dict) -> str — draft a notification using a named template

Output schema:
{
  "severity": "routine" | "elevated" | "urgent",
  "summary": "one-sentence summary of the incident",
  "human_review_required": bool,
  "review_reason": "why a human must review before any action" | null,
  "steps": [
    {
      "id": 1,
      "intent": "natural-language description of what this step accomplishes",
      "tool": "<one of the tools above>",
      "args": { ... tool-specific args ... },
      "depends_on": [list of step ids whose results this step needs]
    }
  ]
}

Be prescriptive. Do not say "look up the weather" — say `web_fetch` with a specific URL. Do not say "check related reports" — say `grep_files` with a specific pattern and path. If you don't know the exact URL or path, leave a placeholder like "<lookup-needed:weather-api-for-grid-18STJ>" so the operator sees what's missing rather than the executor guessing.
"""

# Fictional report — no real PII, no real OPSEC content
SAMPLE_REPORT = """INCIDENT REPORT - TRAINING EXERCISE [FICTIONAL TEST DATA]

DTG: 172347MAY26
LOCATION: Training Area 7, vicinity grid 18S TJ 12345 67890
UNIT: 2nd Platoon, B Company, 1-100 IN BN
INCIDENT TYPE: Trainee separation during night land navigation

NARRATIVE:
At approximately 2230 local, Trainee SMITH, J. (E-2) was reported overdue
at checkpoint Charlie during the night land navigation exercise. Initial
search of last-known route was initiated at 2245 by squad leader SGT JONES.
Trainee was located at 2310 approximately 400m east of expected route,
disoriented and dehydrated but otherwise uninjured. Medic on scene cleared
trainee for transport. Trainee was transported to aid station for evaluation.

Weather conditions at time of incident: light rain, visibility 200m, temp 14C,
wind from NNW at 8kt. Lunar illumination 12%.

Cross-reference: see also report TR-5/2026 (related land nav incident,
same training area, dated 14MAR26).

STATUS: Trainee released to unit at 0145, training continues with modified
night nav route. Recommend review of route marking adequacy and consider
codifying a weather-trigger pause threshold for future night nav iterations.

REPORTING NCO: SFC WILSON, M.
"""


def main() -> int:
    api_key = os.environ.get("GENAI_MIL_API_KEY")
    if not api_key:
        print("GENAI_MIL_API_KEY not set", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": SAMPLE_REPORT},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    print(f"POST {ENDPOINT}  (model: {MODEL})")
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
    print(f"HTTP {resp.status_code}  ({elapsed:.1f}s)")

    if resp.status_code != 200:
        print(resp.text)
        return 1

    body = resp.json()
    usage = body.get("usage", {})
    print(f"tokens: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}")
    print()
    content = body["choices"][0]["message"]["content"]

    try:
        plan = json.loads(content)
        print("=== PARSED PLAN ===")
        print(json.dumps(plan, indent=2))
    except json.JSONDecodeError as e:
        print(f"!!! Output is not valid JSON: {e}")
        print("=== RAW CONTENT ===")
        print(content)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
