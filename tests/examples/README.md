# Sample outputs from prior test runs

Reference artifacts showing what good output looks like from each layer of
the pipeline. Not used at runtime; useful for skimming before making
changes to see what current outputs resemble.

| File | What it is |
|---|---|
| `robustness_results.txt` | Output of `tests/test_robustness.py` run against the 5 fictional sample reports. Shows the full plan JSON for each report plus a summary table. |
| `safety_review_172347MAY26.md` | A markdown safety-review draft that Gemma 4 31B produced end-to-end when run through the full pipeline (`get_plan` → execute → `consult_planner` × 4 → wrote files). Useful as a quality reference. |
| `safety_alert_172347MAY26.log` | The corresponding one-line alert message Gemma wrote when the configured Slack webhook env var wasn't available. Shows the executor's reasonable fallback behavior. |

**All sample data in this directory is fictional.** The scenarios, names and
unit designations are synthetic and were written for testing; nothing here
describes a real incident.

These were captured during the development of this repo and may not reflect
the latest prompt or model behavior. Regenerate by running the tests
yourself to get current outputs.
