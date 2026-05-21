# Tests and testing artifacts

Everything under `tests/` is for validating the planner-mcp; nothing here
is needed at runtime to actually use the MCP. If you're an operator, you
can ignore this directory.

## Layout

| Path | What it is |
|---|---|
| `sample_reports.py` | Five FICTIONAL incident reports covering common command-post categories (trainee separation, vehicle accident, heat casualty, weapon malfunction, ND). Used by `test_robustness.py`. All reports tagged `[FICTIONAL TEST DATA]`. Incident-shaped because the planner-mcp's incident path was the first one validated end-to-end; the MCP itself handles any task shape (see e2e examples in the root README). |
| `test_report.txt` | A single fictional incident report on disk, with cross-references to docs in `references/`. Used by end-to-end tests that invoke OpenCode and need a file to point at. |
| `references/` | Fictional cross-reference documents (`TR-5_2026.md`, `SOP-7-2-3_weather_triggers.md`) that `test_report.txt` references. Lets e2e tests succeed against real files instead of placeholder paths. |
| `test_server_logic.py` | **Primary smoke test.** Exercises all 5 MCP tools end-to-end (triage_only, get_plan, consult_planner, synthesize, draft_output) plus the session-memory flow and the `replan` consult path. Bypasses the stdio/MCP transport — calls the tool functions directly. Takes 2-3 minutes (each Gemini call is 15-30s). |
| `test_robustness.py` | Runs the planner prompt against all five sample reports and prints a summary table. Use this after editing `planner_prompt.py` to confirm you haven't regressed any report category. |
| `iterations/` | Frozen prompt-development history (`test_planner.py` → `_v4.py`). Kept for documentation, not for active testing. See its README. |
| `examples/` | Sample outputs from prior test runs. Useful as reference for what good output looks like. See its README. |

## How to run

From the repo root, with a venv set up and `GENAI_MIL_API_KEY` exported:

```sh
# Primary smoke test — covers everything
.venv/bin/python tests/test_server_logic.py

# Robustness pass after prompt edits — covers all 5 report categories
.venv/bin/python tests/test_robustness.py
```

Both scripts inject the repo root onto `sys.path` so they can import
`server` and `planner_prompt` regardless of CWD.

## End-to-end with an executor

There is no scripted e2e test against an OpenCode-hosted executor in this
repo because it requires access to your local/on-prem LLM endpoints and
varies per environment.
For the manual procedure see the root `README.md` — short version:

```sh
# Incident-shaped task (the most-validated path):
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at tests/test_report.txt and produce \
   a safety officer notification."

# Or any non-incident task — the MCP is general-purpose:
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Read AGENTS.md and server.py and produce a one-page architectural \
   overview for a new contributor."
```

If you script these runs (rather than typing them at a terminal), append
`< /dev/null` — `opencode run` hangs at startup when stdin is a non-TTY
pipe left open by the launcher. See the root `README.md` "Known quirks".

Captured outputs from prior runs are in `tests/examples/`.
