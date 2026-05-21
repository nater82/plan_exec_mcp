"""Smoke test for the MCP server's underlying logic.

Bypasses stdio/MCP transport — FastMCP handles that. Exercises the full
tool surface AND the session-memory flow:

  1. triage_only happy path (Flash model)
  2. get_plan happy path → captures session_id
  3. consult_planner via session_id (no need to re-pass report)
  4. synthesize via session_id with mock step_results
  5. draft_output via session_id with the synthesis
  6. Validation/retry path (synthetic invalid plan)
"""

import json
import sys
from pathlib import Path

# Allow `import server` (at repo root) and `from sample_reports` (in tests/).
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))             # tests/ — for sample_reports
sys.path.insert(0, str(_HERE.parent))      # repo root — for server, planner_prompt

import server  # noqa: E402
from sample_reports import HEAT_CASUALTY  # noqa: E402


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n=== {title}\n{'=' * 70}")


def main() -> int:
    section("1. triage_only happy path (Flash)")
    triage = server.triage_only(HEAT_CASUALTY)
    if "error" in triage:
        print(f"FAILED: {triage}")
        return 1
    for k in ("severity", "summary", "human_review_required", "brief_rationale", "needs_full_planner"):
        print(f"  {k}: {triage.get(k)!r}")

    section("2. get_plan happy path → session_id")
    # available_tools is REQUIRED — a realistic mix of built-ins and an MCP tool.
    available_tools = [
        {"name": "Read", "description": "Read a file. Args: file_path (str, absolute)."},
        {"name": "Glob", "description": "Find files by glob pattern. Args: pattern (str)."},
        {"name": "Grep", "description": "Search file contents with regex. Args: pattern (str), path (str)."},
        {"name": "Bash", "description": "Run a shell command. Args: command (str)."},
        {"name": "toolforge_read_pdf", "description": "Extract text from a PDF file. Args: file_path (str)."},
    ]
    plan = server.get_plan(
        user_intent="produce a CCIR for battalion CDR covering this incident",
        available_tools=available_tools,
        input_text=HEAT_CASUALTY,
    )
    if "error" in plan:
        print(f"FAILED: {plan}")
        return 1
    sid = plan.get("session_id")
    if not sid:
        print(f"FAILED: get_plan did not return a session_id")
        return 1
    print(f"  session_id: {sid}")
    print(f"  summary: {plan['summary'][:120]}")
    print(f"  steps: {len(plan['steps'])}")

    section("3. consult_planner via session_id (no input_text re-passed)")
    consult = server.consult_planner(
        current_step=plan["steps"][1] if len(plan["steps"]) > 1 else plan["steps"][0],
        problem="The referenced HEAT-2025-04 document is not at the path the plan specified. The closest match is /reports/historical/HEAT-2025-04-summary.md.",
        session_id=sid,
    )
    if "error" in consult:
        print(f"FAILED: {consult}")
        return 1
    print(f"  decision: {consult['decision']}")
    print(f"  reasoning (first 150 chars): {consult['reasoning'][:150]}")

    section("4. synthesize via session_id with mock step_results")
    # Step 2 uses file_path — exercises the MCP's server-side file read
    # (the executor passes a path; the MCP reads the file itself).
    sop_ref = _HERE / "references" / "SOP-7-2-3_weather_triggers.md"
    mock_step_results = [
        {
            "id": 1,
            "intent": "Read HEAT-2025-04 prior case",
            "tool": "Read",
            "result": "Similar trainee, also Black Flag conditions, took 6 hours of lane before collapse. Cadre did not suspend training. Trainee recovered fully after 48h observation.",
        },
        {
            "id": 2,
            "intent": "Pull battalion heat/weather SOP (read server-side from file_path)",
            "tool": "Read",
            "file_path": str(sop_ref),
        },
        {
            "id": 3,
            "intent": "Verify range control WBGT logs",
            "tool": "WebFetch",
            "result": "Range control log: WBGT 84 at 1200, 86 at 1230, 88 at 1245, 90 at 1330, 91 at 1345. Lane suspended at 1400.",
        },
    ]
    print(f"  step 2 file_path: {sop_ref}  (exists: {sop_ref.exists()})")
    synth = server.synthesize(step_results=mock_step_results, session_id=sid)
    # synthesize may request more info; run the round-trip until it synthesizes.
    _round = 1
    while isinstance(synth, dict) and synth.get("status") == "needs_more_info" and _round < 5:
        print(f"  round {_round}: needs_more_info — {synth.get('reason', '')[:80]}")
        print(f"    gather_steps: {len(synth.get('gather_steps', []))}")
        synth = server.synthesize(step_results=[], session_id=sid)
        _round += 1
    if "error" in synth:
        print(f"FAILED: {synth}")
        return 1
    if synth.get("status") == "needs_more_info":
        print("FAILED: synthesize still requesting info after the final round")
        return 1
    print(f"  key_findings ({len(synth['key_findings'])}):")
    for f in synth["key_findings"]:
        print(f"    - {f}")
    print(f"  evidence_summary (first 200 chars): {synth['evidence_summary'][:200]}")
    print(f"  gaps_or_uncertainties ({len(synth.get('gaps_or_uncertainties', []))}):")
    for g in synth.get("gaps_or_uncertainties", []):
        print(f"    - {g}")

    section("5. draft_output via session_id + synthesis")
    draft = server.draft_output(
        purpose="safety_officer_notification",
        audience="battalion_safety_officer",
        synthesis=synth,
        session_id=sid,
        extra_guidance="Keep under 250 words. BLUF format.",
    )
    if "error" in draft:
        print(f"FAILED: {draft}")
        return 1
    print(f"  model: {draft['model']}")
    print(f"  draft_text ({len(draft['draft_text'])} chars):")
    print("  ---")
    for line in draft["draft_text"].splitlines():
        print(f"  {line}")
    print("  ---")

    section("6. consult_planner replan path (material finding triggers replan)")
    replan_reply = server.consult_planner(
        current_step={"id": 2, "intent": "Read battalion heat SOP", "tool": "Read", "args": {"file_path": "tests/references/SOP-7-2-3_weather_triggers.md"}, "depends_on": []},
        problem=(
            "I just read the SOP. It specifies VISIBILITY < 200m requires SUSPEND (not pause) "
            "of all outdoor training. The incident report says visibility was exactly 200m, which "
            "is the boundary of the SUSPEND threshold. Combined with the 12% lunar illumination "
            "(below the 15% PAUSE threshold for night land nav), the training should have been "
            "suspended BEFORE the trainee separation occurred. This makes the incident a clear "
            "double-SOP-violation, not just an environmental accident. The remaining plan steps "
            "(generic safety notification) don't address this — they should focus on the SOP "
            "violation and recommend disciplinary review."
        ),
        session_id=sid,
    )
    if "error" in replan_reply:
        print(f"FAILED: {replan_reply}")
        return 1
    print(f"  decision: {replan_reply['decision']}")
    print(f"  reasoning: {replan_reply['reasoning'][:200]}")
    if replan_reply["decision"] == "replan":
        steps = replan_reply.get("revised_remaining_steps") or []
        print(f"  revised_remaining_steps ({len(steps)}):")
        for s in steps:
            print(f"    - id={s.get('id')} tool={s.get('tool')} intent={s.get('intent', '')[:60]!r}")

    section("7. Validation/retry (synthetic invalid plan)")
    bad = {
        "summary": "",
        "human_review_required": "yes",
        "steps": [{"id": "one", "tool": "shoot_lasers", "args": "stuff"}],
    }
    errors = server._validate_plan(bad, allowed_tools={"Read", "Write", "Bash"})
    print(f"  Detected {len(errors)} errors in synthetic bad plan:")
    for e in errors:
        print(f"    - {e}")
    if len(errors) < 4:
        print("FAILED: expected validator to catch several issues")
        return 1

    section("MODEL ASSIGNMENT (from env / defaults)")
    for tool, model in server.MODELS.items():
        print(f"  {tool}: {model}")

    section("ALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
