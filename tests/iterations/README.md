# Prompt-development iteration history

These scripts are **frozen artifacts** from the original prompt-development
session. They show how the working planner prompt was reached. They are NOT
expected to run cleanly against the current `planner_prompt.py` because the
prompt has evolved since each iteration was captured.

The history is useful as documentation of what was tried and why — useful
to skim before you make significant prompt changes, to avoid re-walking
the same dead ends.

## The iterations

| File | What happened |
|---|---|
| `test_planner.py` (v1) | Initial attempt. Used `response_format: {"type": "json_object"}` to enforce JSON output. **Failed:** genai.mil silently ignored the parameter and the model produced a conversational "let me know how I can help" response. |
| `test_planner_v2.py` (v2) | Moved format instructions into the user message; added an explicit "first char `{`, last char `}`" directive; added a one-shot example. **Worked:** clean JSON, plan with 2 steps. Minimal but right shape. |
| `test_planner_v3.py` (v3) | Removed the example, replaced with a categorical "include steps for X, Y, Z" checklist. **Failed:** Without the example, Gemini defaulted to extracting the report's fields into structured JSON instead of producing a plan with steps. **The example is load-bearing — do not remove it.** |
| `test_planner_v4.py` (v4) | Reintroduced the example, made it richer with 5-6 steps covering multiple categories. **Worked:** clean JSON, comprehensive plans, generalized across all 5 sample report categories in the robustness test. v4's prompt is the basis for the current `planner_prompt.py`. |

## Key lessons from this history

1. **`response_format: json_object` is a no-op on genai.mil** — don't rely on it for output formatting.
2. **The example is the prompt** — categorical guidance and schema definitions alone don't anchor the model's output shape. A good example does.
3. **Format directives belong in the user message, not just the system prompt** — Gemini weights user-message instructions higher than system-prompt ones.
4. **More steps in the example anchors more steps in the output** — v2's 3-step example produced 2-step outputs; v4's 5-6 step example produced 5-6 step outputs.

When iterating on `planner_prompt.py`, change the example first, then run
`tests/test_robustness.py` to confirm the change doesn't regress the other
report categories.
