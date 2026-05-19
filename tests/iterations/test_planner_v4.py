"""v4: richer example to anchor toward comprehensive plans.

v3 finding: removing the example caused Gemini to extract-not-plan.
The example anchors the model's understanding of what "plan" means
in this context. The categorical guidance alone wasn't enough.

v4: reinstate the example with a 5-step plan demonstrating all
required categories (context, environment, pattern, alert, draft).
Keep the categorical guidance as backup.
"""

import json
import os
import re
import sys
import time

import requests

ENDPOINT = "https://api.genai.mil/v1/chat/completions"
MODEL = "gemini-3.1-pro-preview"

PLANNER_SYSTEM = """You are a triage planner for command post incident reports during military training operations. You produce structured JSON plans that a separate executor agent (a less-capable model with tool calling) will follow step by step.

Your job is NOT to investigate — it is to plan the investigation. The executor cannot make judgment calls; it just runs the steps you give it. Be prescriptive and comprehensive.

Available executor tools:
- web_fetch(url: str) -> str
- read_file(path: str) -> str
- grep_files(pattern: str, path: str) -> list[str]
- post_alert(channel: str, severity: str, message: str) -> str
- draft_report(template: str, fields: dict) -> str

A good plan addresses every notable element of the report. Err toward more steps. If the report mentions weather, look up weather. If it references another report, pull that report. If it has recommendations, document them. Skipping these is a defect.
"""

EXAMPLE = """EXAMPLE — a different fictional report and the plan you would produce:

INPUT REPORT:
"DTG: 040614MAY26. TA-3 access road. HMMWV slid on wet pavement at 0410.
Driver SPC JONES bumped head, no LOC. Vehicle drivable. Light rain ongoing.
See also AAR-2025-11 (winter weather driver training)."

YOUR OUTPUT (clean JSON, no preamble, no fences):
{
  "severity": "elevated",
  "summary": "HMMWV slide on wet pavement, driver minor head contact no LOC.",
  "human_review_required": true,
  "review_reason": "Vehicle accident with personnel impact requires safety officer review per SOP.",
  "steps": [
    {
      "id": 1,
      "intent": "Read source incident report into context",
      "tool": "read_file",
      "args": {"path": "/reports/incoming/<incident-filename>"},
      "depends_on": []
    },
    {
      "id": 2,
      "intent": "Pull referenced prior document AAR-2025-11 on winter weather driver training",
      "tool": "read_file",
      "args": {"path": "/references/AAR-2025-11.md"},
      "depends_on": []
    },
    {
      "id": 3,
      "intent": "Look up road/weather conditions on TA-3 around 0410 to corroborate the report",
      "tool": "web_fetch",
      "args": {"url": "<lookup-needed:weather-api-for-TA-3-coords-on-040410MAY26>"},
      "depends_on": []
    },
    {
      "id": 4,
      "intent": "Check for prior accident reports on TA-3 access road in past 90 days to detect a pattern",
      "tool": "grep_files",
      "args": {"pattern": "(TA-3|access road).*(slide|accident|HMMWV)", "path": "/reports/"},
      "depends_on": []
    },
    {
      "id": 5,
      "intent": "Post info-level notification to safety channel",
      "tool": "post_alert",
      "args": {"channel": "safety-officer", "severity": "info", "message": "Elevated incident: HMMWV slide on TA-3 access road, no LOC. Triage in progress, report forthcoming."},
      "depends_on": [1]
    },
    {
      "id": 6,
      "intent": "Draft safety officer notification with full context once prior data is in hand",
      "tool": "draft_report",
      "args": {"template": "safety_officer_notification", "fields": {"incident_type": "vehicle_accident", "injury_summary": "head_bump_no_loc", "personnel": "SPC JONES"}},
      "depends_on": [1, 2, 3, 4]
    }
  ]
}
"""

USER_INSTRUCTION_TEMPLATE = """{example}

NOW PROCESS THIS REPORT:

{report}

Respond with ONLY the JSON plan. Do not write any preamble, summary, offer to help, or explanation. Do not wrap the JSON in markdown code fences. The first character of your response must be `{{` and the last must be `}}`."""

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


def main() -> int:
    api_key = os.environ.get("GENAI_MIL_API_KEY")
    if not api_key:
        print("GENAI_MIL_API_KEY not set", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": USER_INSTRUCTION_TEMPLATE.format(example=EXAMPLE, report=SAMPLE_REPORT)},
        ],
        "temperature": 0.1,
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

    plan = extract_json(content)
    if plan is None:
        print("!!! Could not extract JSON from response")
        print("=== RAW CONTENT ===")
        print(content)
        return 1

    is_clean = content.strip().startswith("{") and content.strip().endswith("}")
    step_count = len(plan.get("steps", []))
    print(f"Clean JSON output: {is_clean}")
    print(f"Steps: {step_count}")
    print()
    print("=== PARSED PLAN ===")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
