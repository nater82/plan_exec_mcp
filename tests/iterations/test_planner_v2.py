"""v2: stronger format enforcement.

v1 findings:
- response_format: json_object was silently ignored by genai.mil
- Gemini defaulted to conversational helper mode despite system-prompt
  instructions to produce structured output
- Reading comprehension was fine; output discipline was the failure

v2 changes:
- Move format instruction into the user message (Gemini weights this higher)
- Provide a one-shot example of expected output
- Explicit "no preamble, no markdown" directive
- Add a code-fence-tolerant JSON extractor as a fallback parser
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

Your job is NOT to investigate — it is to plan the investigation. The executor cannot make judgment calls; it just runs the steps you give it. Be prescriptive.

Available executor tools:
- web_fetch(url: str) -> str
- read_file(path: str) -> str
- grep_files(pattern: str, path: str) -> list[str]
- post_alert(channel: str, severity: str, message: str) -> str
- draft_report(template: str, fields: dict) -> str
"""

ONE_SHOT_EXAMPLE = """EXAMPLE INPUT (a different fictional report):
"At 0410, vehicle accident reported on TA-3 access road. HMMWV slid on
wet pavement. Driver SPC JONES bumped head, no LOC. Vehicle drivable."

EXAMPLE OUTPUT (this exact format, no preamble, no markdown fences):
{
  "severity": "elevated",
  "summary": "HMMWV slide on wet pavement, minor head bump, no loss of consciousness.",
  "human_review_required": true,
  "review_reason": "Vehicle accident with personnel injury requires safety officer notification per SOP.",
  "steps": [
    {
      "id": 1,
      "intent": "Pull weather/road conditions for TA-3 access road around 0410",
      "tool": "web_fetch",
      "args": {"url": "<lookup-needed:weather-api-for-TA-3>"},
      "depends_on": []
    },
    {
      "id": 2,
      "intent": "Check for prior accident reports on this access road in past 90 days",
      "tool": "grep_files",
      "args": {"pattern": "TA-3.*access.*accident", "path": "/reports/"},
      "depends_on": []
    },
    {
      "id": 3,
      "intent": "Draft safety officer notification using the head-injury-no-LOC template",
      "tool": "draft_report",
      "args": {"template": "safety_officer_notification", "fields": {"injury_type": "head_bump_no_loc", "personnel": "SPC JONES"}},
      "depends_on": [1, 2]
    }
  ]
}
"""

USER_INSTRUCTION_TEMPLATE = """{example}

NOW PROCESS THIS REPORT:
{report}

Respond with ONLY the JSON object. Do not write any preamble, summary, offer to help, or explanation. Do not wrap the JSON in markdown code fences. The first character of your response must be `{{` and the last must be `}}`. If you would normally add commentary, suppress it — the executor parses your output as JSON directly and any non-JSON text will cause it to fail."""

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
    """Try several strategies to pull JSON out of the model's response."""
    # Strategy 1: whole response is JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: JSON inside ```json ... ``` or ``` ... ``` fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first {...} block in the response
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

    user_message = USER_INSTRUCTION_TEMPLATE.format(
        example=ONE_SHOT_EXAMPLE,
        report=SAMPLE_REPORT,
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": user_message},
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
    print(f"Clean JSON output (no wrapping): {is_clean}")
    print()
    print("=== PARSED PLAN ===")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
