# plan_exec_mcp

An MCP server that exposes Gemini (via genai.mil) as the **cognitive layer**
for executor agents (GPT-OSS 120B, Gemma 4 31B, etc.) running in OpenCode
or any MCP-capable harness.

The architecture pattern is **planner-executor**:

> **The strong model (Gemini, via genai.mil) does the thinking.
> The weaker local model (the executor) does the tool calling
> — running plan steps, gathering information, ferrying results back.**

Useful when your executor isn't capable enough to plan well on its own,
or when you want to concentrate cognitive work in a single high-quality
model for cost and consistency.

## Repo layout

```
.
├── server.py               # The MCP server itself
├── planner_prompt.py       # All tool prompts (system + example + template)
├── requirements.txt        # mcp, requests
├── SETUP.md                # Newcomer-friendly step-by-step setup guide
├── config/                 # OpenCode config templates — see config/README.md
│   ├── providers.example.json   # genai.mil + example local/on-prem executor providers
│   ├── opencode.example.json    # MCP registration (templated paths)
│   ├── AGENTS.example.md        # Optional executor-side prompt addendum
│   └── README.md
├── docs/
│   └── WSL_SETUP.md        # Windows → WSL → working setup walkthrough
├── scripts/
│   ├── setup.py            # Interactive: venv + templates + healthcheck
│   └── healthcheck.py      # Verifies genai.mil endpoint + key + each model
└── tests/                  # Everything testing-related — see tests/README.md
    ├── sample_reports.py        # Fictional reports for robustness testing
    ├── test_report.txt          # Sample report used by e2e tests
    ├── test_server_logic.py     # Smoke test for all 5 tools + session flow
    ├── test_robustness.py       # Planner across all sample reports
    ├── references/         # Fictional cross-reference docs that test reports point to
    ├── iterations/         # Frozen prompt-development history
    └── examples/           # Sample outputs from prior runs
```

The clean split: **root, `config/`, `docs/`, and `scripts/` are what an
operator needs; `tests/` is for validating changes.**

## What the MCP exposes

Five tools, ordered by typical use:

| Tool | What Gemini does | Default model | When to call |
|---|---|---|---|
| `triage_only(report)` | Fast severity + summary classification. | **Gemini Flash** | First, gates whether to invoke the full pipeline. |
| `get_plan(report, available_tools?)` | Authoritative multi-step JSON plan. Returns a `session_id`. | Gemini Pro | After triage, when the report warrants full processing. |
| `consult_planner(current_step, problem, session_id)` | Mid-execution arbiter. Returns `proceed`/`revise`/`skip`/`escalate`. | Gemini Pro | Whenever the executor gets stuck. |
| `synthesize(step_results, session_id)` | Structured analytical synthesis after execution. | Gemini Pro | After all plan steps complete. |
| `draft_output(purpose, audience, synthesis, session_id)` | Polished prose for human consumption. | Gemini Pro | Last, before showing output to a human. |

Each tool comes in **two description styles** toggled via `PLANNER_TOOL_STYLE`:
- `heavy` (default) — strong push to consult; default-deny on freelancing
- `light` — neutral, lets the executor decide when to use the tools

Session memory: `get_plan` returns a `session_id`. Subsequent tools accept
that id and pull the report/plan/tool-list from server-side memory instead
of re-passing everything on the wire.

## Easy model swapping

Every tool reads its model from an env var. To swap when genai.mil adds a
new model, change **one** env var — no code edit.

| Tool | Env var | Default |
|---|---|---|
| (global default) | `PLANNER_MODEL` | `gemini-3.1-pro-preview` |
| `get_plan` | `PLANNER_MODEL_GET_PLAN` | `$PLANNER_MODEL` |
| `consult_planner` | `PLANNER_MODEL_CONSULT_PLANNER` | `$PLANNER_MODEL` |
| `synthesize` | `PLANNER_MODEL_SYNTHESIZE` | `$PLANNER_MODEL` |
| `draft_output` | `PLANNER_MODEL_DRAFT_OUTPUT` | `$PLANNER_MODEL` |
| `triage_only` | `PLANNER_MODEL_TRIAGE_ONLY` | `gemini-3-flash-preview` |

The server prints its per-tool model assignment to stderr at startup, and
`scripts/healthcheck.py` checks every model the server is configured to use.

## Quickstart

Prerequisites: Linux/macOS/WSL terminal, Python 3.10+, `npm` (for OpenCode),
a working `git`, and a `GENAI_MIL_API_KEY`. Windows users without WSL: start
with [`docs/WSL_SETUP.md`](docs/WSL_SETUP.md). Less-technical users wanting
a hand-held walkthrough: [`SETUP.md`](SETUP.md).

```sh
# 1. Clone, install, set key
git clone git@github.com:nater82/plan_exec_mcp.git
cd plan_exec_mcp
export GENAI_MIL_API_KEY=your-key   # add to ~/.bashrc to persist

# 2. Interactive setup: venv, deps, global MCP registration, providers,
#    healthcheck. It offers to add the provider blocks for you (a safe merge
#    that won't touch providers you already have).
python3 scripts/setup.py

# 3. Edit the placeholder endpoint URLs that setup added for org-gptoss /
#    org-gemma in ~/.config/opencode/opencode.json — point them at your
#    real on-prem models.

# 4. Use it, from any directory. The --model is the EXECUTOR — a LOCAL model
#    that runs on your machine; never a genai-mil/gemini-* model.
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at tests/test_report.txt and produce a safety officer notification."

# Or a non-incident task:
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Read AGENTS.md and server.py and produce an architectural overview for a new contributor."
```

The MCP is **self-contained** — it needs no `AGENTS.md` to function (you do
register it once in OpenCode's config; see setup). Heavy tool descriptions
push both GPT-OSS 120B and Gemma 4 31B to engage the MCP naturally on
substantive tasks (incident reports, multi-source synthesis, formatted
artifacts) and to correctly skip it on trivial ones (one-line lookups,
simple summaries). Every plan the planner emits ends with `synthesize` and
`draft_output` calls, so the executor's "execute the plan" mode drives
completion automatically.

**The executor vs. the planner.** The model you pass to `--model` (or pick
via `/models` in an interactive session) is the **executor** — it runs on
your machine and does the tool calls. It must be a **local/on-prem** model.
Gemini is the **planner**, reached by the MCP server internally; you never
select it with `--model`. Passing a `genai-mil/gemini-*` model as the
executor breaks local file access — Gemini runs remotely.

`config/AGENTS.example.md` is an **optional** executor-side system-prompt
addendum. It nudges the executor harder on borderline tasks (e.g.
moderately-complex summaries that could go either way) and helps with
recovery when steps fail. Install it if you want stronger MCP-engagement
on ambiguous tasks; skip it otherwise.

```sh
# optional — install only if you want extra MCP-engagement push
cp config/AGENTS.example.md AGENTS.md
```

## Prompting tips

**Magic phrase for guaranteed MCP engagement:** prefix your request with
`"Use the planner-mcp tools to ..."` or `"Use the planner-mcp for this
task ..."`. This reliably routes through the pipeline (triage → plan →
execute → synthesize → draft) regardless of how the executor would
otherwise judge task complexity. Useful when you want consistent,
structured output rather than the executor's freelance summary.

Without the prefix, the executor self-judges:
- Substantive tasks (incident reports, multi-doc research, cross-references) → usually engages MCP on its own
- Trivial tasks (one-line lookups, simple summaries) → handles directly, no MCP overhead
- Borderline (research-y questions, ambiguous) → variable; depends on the model and the day

Both behaviors are usually correct. The prefix is for when you want to override the executor's judgment.

**Example invocations:**

```sh
# Incident triage (engages MCP without the prefix; magic phrase optional but harmless):
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at tests/test_report.txt and produce a CCIR."

# Research/analysis with the magic prefix (forces MCP):
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Use the planner-mcp tools to research the opencode project at <path>. \
   Produce a technical overview covering architecture, key components, and design choices."

# Document revision:
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Use the planner-mcp to revise this CONOP draft using supporting docs in ./references/."
```

## Known quirks

- **Executor short-circuits on tasks it judges trivial.** Not a bug — this is intended behavior. Use the magic phrase to override.
- **Synthesize and draft_output occasionally fail with JSON parse errors** when the executor injects chat-template tokens into the args (e.g. GPT-OSS's `<|...` Harmony tokens, Gemma's `<|"|`). The executor usually recovers by writing the analysis itself; quality is often still good. Worst case: re-run, or use a different executor.
- **First Gemini call after idle returns HTTP 401 "key locked".** The unlock URL appears in the error body. Click it once, key is re-enabled. Re-run `scripts/healthcheck.py` to confirm.
- **2-3 min wall time is normal** for a full pipeline. The 30-60s opaque pause during `synthesize` is expected — the model is working, not stuck. If a single tool is stuck >90s, suspect network or rate limits.
- **GPT-OSS 120B is the supported executor.** Gemma 4 31B cannot reliably drive the planner-mcp: it fails the `get_plan` tool call with malformed-tool-call errors and falls back to handling the task on its own (often with chat-template token leakage in the output). Use `org-gptoss/openai/gpt-oss-120b` or an equivalent capable model as the executor; treat Gemma as unsupported for the MCP workflow.
- **`triage_only` is incident-shaped only.** For research, summarization, code, document analysis tasks, the executor skips it and goes straight to `get_plan`. That's correct.
- **Restart OpenCode after editing `~/.config/opencode/opencode.json`** — the MCP block is read at startup, not hot-reloaded.
- **Headless `opencode run` from a script needs stdin redirected.** OpenCode 1.4.3 blocks reading stdin to EOF at startup when stdin is not a TTY (`run.ts` does `await Bun.stdin.text()`). Typed interactively in a terminal it's fine — stdin is a TTY. But from a script, cron, CI, or any non-interactive launcher that leaves stdin open, append `< /dev/null`: `opencode run --model … "prompt" < /dev/null`. Without it the process hangs at startup before doing anything — no output, no error.

**To iterate on prompt quality:** edit `planner_prompt.py` (the EXAMPLE is
the primary anchor — see `tests/iterations/README.md` for why) and rerun
`tests/test_robustness.py`.

**To swap planner models** (e.g. when genai.mil adds a new one): set
`PLANNER_MODEL=<new-model>` in your shell, or override per-tool with
`PLANNER_MODEL_GET_PLAN`, `PLANNER_MODEL_TRIAGE_ONLY`, etc. No code edit
needed.

## Expected latency

A full pipeline run (`triage → get_plan → execute → synthesize → draft_output`)
typically takes **2-3 minutes** of wall time. Individual Gemini calls range
from ~5s (Flash triage) to 30-60s (Pro synthesize/draft). The longest single
opaque pause is `synthesize` — 30-60s where OpenCode shows only a spinner.

OpenCode displays each tool call as it's invoked, so you can follow progress
between Gemini calls. If a single tool appears stuck for **more than ~90s**,
suspect a network blip, a rate limit, or a locked API key — run
`scripts/healthcheck.py` to confirm the endpoint is responsive.

If you need to trade quality for speed: override per-tool models via env vars
(see Config knobs below). Dropping `synthesize` and/or `draft_output` to
Gemini Flash roughly halves their latency at some loss of output quality.

## Config knobs

| Env var | Default | Purpose |
|---|---|---|
| `GENAI_MIL_API_KEY` | — | **Required.** API key for genai.mil. |
| `PLANNER_MODEL` | `gemini-3.1-pro-preview` | Global default model. |
| `PLANNER_MODEL_<TOOL>` | — | Per-tool override. `<TOOL>` ∈ `GET_PLAN`, `CONSULT_PLANNER`, `SYNTHESIZE`, `DRAFT_OUTPUT`, `TRIAGE_ONLY`. |
| `PLANNER_TOOL_STYLE` | `heavy` | `heavy` or `light` tool descriptions. |
| `PLANNER_HTTP_TIMEOUT` | `180` | Seconds before the genai.mil request times out. |
| `PLANNER_ALLOW_INFO_REQUESTS` | `1` | When on, `synthesize` may return a `needs_more_info` request that the executor fulfills and re-calls. Set to `0` to force a single-pass synthesis with no round-trip — useful for one-shot runs or latency-sensitive automation where the extra executor turns are undesirable. |
| `PLANNER_MCP_TOOL_PREFIX` | `planner-mcp-heavy_` | The prefix OpenCode uses for this MCP's tools (matches whatever name you registered it under in `opencode.json`). The planner uses this to name the synthesize/draft steps in plans. If your MCP block is named differently (e.g. `planner-mcp-light` or just `planner`), set this to that name with a trailing underscore. |

## Design notes

- **Why the MCP reads files itself (incl. PDF/Office).** `synthesize` and
  `get_plan`'s `input_files` take file *paths*; the MCP server reads them.
  For `.pdf/.docx/.xlsx/.pptx` it parses the document into text server-side
  (`pypdf`, `python-docx`, `openpyxl`, `python-pptx`). The weak executor
  never has to read or parse a document — it just hands over a path. This
  exists because executors mangle large file contents when ferrying them,
  and cannot parse compressed formats (a raw byte read of a PDF/Office file
  is unrecoverable garbage — verified). If a parser library is missing the
  server returns a clear "install X" marker rather than crashing.
- **Why session memory?** Without it, every tool call after `get_plan` has
  to re-pass `user_intent`, `input_text`, and the plan. Wire-level prompt
  sizes balloon as step_results accumulate. Session memory keeps the
  handoffs small.
- **Why JSON output everywhere except `draft_output`?** The executor parses
  responses programmatically. Free-form prose would force it to do its own
  structured extraction — exactly the cognitive work we want to keep on the
  planner side. `draft_output` is the exception because its consumer is a
  human.
- **Why heavy descriptions by default?** Empirically: with heavy wording,
  both GPT-OSS 120B and Gemma 4 31B reach for the planner unprompted on
  substantive tasks (incident reports, multi-source synthesis, formatted
  artifacts) without needing any AGENTS.md push. They also correctly skip
  the MCP on trivial tasks (one-line lookups, simple summaries) where the
  2-3 min latency would be net-negative. The light style is provided for
  comparison/A-B testing if you want to validate the heavy push is actually
  doing something — usually it is.
- **Why synthesize and draft_output are IN the plan rather than separate
  tool calls?** OpenCode has no hard iteration cap (the default is
  `Infinity`); when an executor "stops early" without producing analysis or
  a draft, that's the model choosing to stop rather than calling another
  tool. By making synthesize and draft_output the last two steps of the
  plan, the executor's natural "execute the plan" mode drives completion
  when the prior steps succeed. AGENTS.md is recommended for graceful
  handling of step failures (e.g. referenced files the planner guessed
  paths for that don't exist); the in-plan approach handles the "happy
  path completion" half of the problem on its own.
- **Latency budget.** Each Gemini call is 15-30s. A full flow of
  `(triage →) plan → execute → (consult →) synthesize → draft` stacks to
  2-3 minutes of Gemini time before counting executor-side tool execution.
  Fine for interactive use where the operator is reading the output
  carefully; for higher-throughput automation, consider parallelizing
  where dependencies allow or switching the heavier steps to Flash.
- **Single point of failure on Gemini.** Pushing more cognitive work to the
  planner concentrates the risk: if genai.mil is unavailable, the executor
  has no fallback (especially for weak executors like Gemma). Worth a
  fallback prompt for "MCP unavailable, do your best."
