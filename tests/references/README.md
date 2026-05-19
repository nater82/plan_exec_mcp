# tests/references/

Fictional reference documents used by the e2e tests to provide the planner
and executor with realistic cross-reference targets. None of this is real
content; all reports/SOPs are fabricated for testing purposes.

When the planner reads a report like `tests/test_report.txt` and sees a
cross-reference (e.g. "see also TR-5/2026"), it generates plan steps that
look for that document. With these reference files in place, those plan
steps succeed and the executor can carry the pipeline through to
synthesize and draft_output. Without them, the plan would fail at the
first Read step (which is what happened in earlier testing).

## What's here

| File | Purpose |
|---|---|
| `TR-5_2026.md` | The "prior land nav incident" referenced in `tests/test_report.txt`. Same training area, similar conditions; gives the synthesize step pattern data. |
| `SOP-7-2-3_weather_triggers.md` | Battalion weather-trigger SOP — gives the synthesize step the specific thresholds it can validate against (visibility, lunar illumination, etc.). |

To add more reference docs for testing other report categories: drop them
here as markdown and update the corresponding test report's cross-references
to mention them.
