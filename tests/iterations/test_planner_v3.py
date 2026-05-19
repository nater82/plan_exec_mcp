"""v3: push for comprehensive plans via category checklist.

v2 findings:
- Format problem solved — clean JSON every time
- Plan quality was too minimal (2 steps, ignored weather, no alerts)
- Likely anchoring on the example's brevity

v3 changes:
- Drop the one-shot example (saves ~400 tokens AND removes the brevity anchor)
- Add explicit step category checklist with "consider including" language
- Add "err toward more steps, not fewer" directive
- Add stronger instruction to address every notable element in the report
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

PLAN STRUCTURE — output a JSON object with exactly these keys:
{
  "severity": "routine" | "elevated" | "urgent",
  "summary": "one-sentence summary",
  "human_review_required": bool,
  "review_reason": string or null,
  "steps": [ { "id": int, "intent": str, "tool": str, "args": {...}, "depends_on": [int, ...] }, ... ]
}

COMPREHENSIVENESS — consider including steps for ALL of these categories that apply to the report:
1. Context gathering — read the source report and any referenced documents (use read_file or grep_files on specific named references, not just keyword searches)
2. Environmental factors — if the report mentions weather, terrain, time of day, or lighting, look those up (web_fetch with a specific URL placeholder if you don't know the exact endpoint)
3. Pattern detection — search for prior similar incidents (grep_files with patterns that would match the incident type or location, not just literal filenames)
4. Notifications — post_alert for any incident classified as elevated or urgent; choose severity and channel based on the incident
5. Documentation — draft_report for any required formal output (AAR, safety officer notification, chain-of-command memo)
6. Root cause flags — if the report contains recommendations or hints at systemic issues, include a step to document those for follow-up

Err toward MORE steps, not fewer. A plan with 6 well-scoped steps is better than a plan with 2 broad ones. The executor cannot infer what you left out.
"""

USER_INSTRUCTION_TEMPLATE = """Process this incident report:

{report}

Respond with ONLY the JSON object. Do not write any preamble, summary, offer to help, or explanation. Do not wrap the JSON in markdown code fences. The first character of your response must be `{{` and the last must be `}}`."""

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
            {"role": "user", "content": USER_INSTRUCTION_TEMPLATE.format(report=SAMPLE_REPORT)},
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
    print(f"Clean JSON output: {is_clean}")
    step_count = len(plan.get("steps", []))
    print(f"Steps: {step_count}")
    print()
    print("=== PARSED PLAN ===")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
