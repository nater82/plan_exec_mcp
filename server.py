"""Planner MCP server.

Exposes Gemini (via genai.mil) as the cognitive layer for executor agents
(GPT-OSS 120B, Gemma 4 31B, etc.) running in OpenCode or any MCP-capable
harness. The executor handles tool calling; the planner handles thinking.

Tools (in order of typical use):
  - triage_only(input_text)
      Lightweight severity classification for INCIDENT-shaped reports only.
      Skip for research/summarization/code/general tasks. Defaults to Gemini
      Flash for speed/cost.

  - get_plan(user_intent, available_tools, input_text="")
      Returns a structured multi-step JSON plan + a session_id. The plan
      always ends with synthesize + draft_output as final steps. Save the
      session_id and pass it to subsequent tools. `user_intent` (verbatim
      request) and `available_tools` (every tool the executor can call,
      built-ins AND MCP tools) are both REQUIRED; the planner only plans
      with tools it is told about. `input_text` may be empty for
      open-ended tasks. available_tools is cached in the session and reused
      by consult_planner.

  - consult_planner(current_step, problem, session_id=None,
                    user_intent=None, input_text=None)
      Mid-execution arbiter. Returns proceed | revise | replan | skip | escalate.
      Call on step failure OR when uncovering material info that may
      change the rest of the plan.

  - synthesize(step_results, session_id=None,
               user_intent=None, input_text=None, plan=None)
      After plan execution, produces a structured analytical synthesis
      (key_findings, evidence_summary, gaps_or_uncertainties). For
      incident-shaped tasks, severity is expressed in the prose; the
      separate triage_only tool produces structured severity classifications.

  - draft_output(purpose, audience, synthesis, session_id=None,
                 user_intent=None, input_text=None, extra_guidance="")
      Generates polished prose drafts (notifications, CCIRs, memos,
      summaries, research write-ups, CONOPs, code explanations — driven by
      the supplied purpose and audience). Where Gemini's writing quality
      pays off most visibly.

Two description styles toggled via PLANNER_TOOL_STYLE:
  - "heavy" (default) — strong push to consult; default-deny on freelancing
  - "light"           — neutral, lets the executor decide

Run via stdio (OpenCode default):
    GENAI_MIL_API_KEY=... python server.py

Model selection — every tool reads its model from env, with a sensible
default. Override per-tool to mix models (e.g. Flash for triage):
    PLANNER_MODEL=gemini-3.1-pro-preview         (global default)
    PLANNER_MODEL_TRIAGE_ONLY=gemini-3-flash-preview
    PLANNER_MODEL_GET_PLAN=gemini-3.1-pro-preview
    PLANNER_MODEL_CONSULT_PLANNER=gemini-3.1-pro-preview
    PLANNER_MODEL_SYNTHESIZE=gemini-3.1-pro-preview
    PLANNER_MODEL_DRAFT_OUTPUT=gemini-3.1-pro-preview

When genai.mil adds new models, swap by setting one env var. No code change.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
from typing import Any, Callable

import requests
from mcp.server.fastmcp import FastMCP

from planner_prompt import (
    DEFAULT_AVAILABLE_TOOLS,
    DRAFT_OUTPUT_TOOL_NAME,
    SYNTHESIZE_TOOL_NAME,
    build_consult_messages,
    build_draft_messages,
    build_messages,
    build_synthesize_messages,
    build_triage_messages,
)

# ---- Config ---------------------------------------------------------------

ENDPOINT = "https://api.genai.mil/v1/chat/completions"
DESCRIPTION_STYLE = os.environ.get("PLANNER_TOOL_STYLE", "heavy")
HTTP_TIMEOUT = float(os.environ.get("PLANNER_HTTP_TIMEOUT", "180"))
RETRY_ON_VALIDATION_FAILURE = True

# When enabled (default), synthesize may return a `needs_more_info` request
# that the executor fulfills with extra gather steps, then re-calls synthesize.
# Disable it (PLANNER_ALLOW_INFO_REQUESTS=0) to force synthesize to always
# produce a synthesis in a single pass — useful for one-shot / headless runs
# where the extra round-trip is undesirable.
_INFO_REQUESTS_ENABLED = os.environ.get(
    "PLANNER_ALLOW_INFO_REQUESTS", "1"
).strip().lower() not in ("0", "false", "no", "off")

# Single default; per-tool overrides via PLANNER_MODEL_<TOOL_NAME_UPPER>
DEFAULT_MODEL = os.environ.get("PLANNER_MODEL", "gemini-3.1-pro-preview")

# Triage defaults to Flash (faster, cheaper) since the task is simpler;
# everything else defaults to whatever PLANNER_MODEL is set to.
_TOOL_MODEL_DEFAULTS = {
    "get_plan": DEFAULT_MODEL,
    "consult_planner": DEFAULT_MODEL,
    "synthesize": DEFAULT_MODEL,
    "draft_output": DEFAULT_MODEL,
    "triage_only": os.environ.get(
        "PLANNER_MODEL_TRIAGE_ONLY", "gemini-3-flash-preview"
    ),
}

MODELS = {
    tool: os.environ.get(f"PLANNER_MODEL_{tool.upper()}", default)
    for tool, default in _TOOL_MODEL_DEFAULTS.items()
}

ALLOWED_SEVERITY = {"routine", "elevated", "urgent"}
ALLOWED_DECISIONS = {"proceed", "revise", "replan", "skip", "escalate"}

# synthesize may request more information across up to this many rounds total;
# the final round is forced to produce a synthesis (guards against loops).
MAX_SYNTHESIZE_ROUNDS = 3

# ---- Tool descriptions ----------------------------------------------------

GET_PLAN_DESC = {
    "heavy": (
        "REQUIRED whenever you receive a task that needs full processing. "
        "Returns the authoritative multi-step plan AND a session_id you must save "
        "for subsequent calls. The plan ALWAYS ends with two steps that call back "
        "into this MCP (synthesize, then draft_output) — execute those just like any "
        "other plan step. You are NOT authorized to investigate, analyze, or draft "
        "independently; the planner determines what to do. Call this FIRST. "
        "YOU MUST PASS TWO THINGS. (1) `user_intent`: the user's actual request "
        "words, verbatim (e.g. 'produce a safety officer notification', 'draft a "
        "CCIR') — do not paraphrase. (2) `available_tools`: the COMPLETE list of "
        "every tool you have access to — built-ins AND every MCP tool (file "
        "readers such as toolforge_read_pdf, search tools, etc.) — as "
        "[{\"name\": str, \"description\": str}, ...] where each description "
        "states what the tool does and its argument names and types. The planner "
        "builds steps ONLY from tools you list here: omit a tool (e.g. a PDF "
        "reader) and the plan can never use it. If the task centres on specific "
        "local files, pass their paths as `input_files` (a list) instead of "
        "pasting file contents into `input_text` — the MCP reads them. Do not "
        "skip or substitute steps without consulting again."
    ),
    "light": (
        "Generate a structured plan. Returns JSON with summary, steps (always ending "
        "with synthesize and draft_output), and a session_id for use with related "
        "tools. Pass `user_intent` (the user's request, verbatim) and "
        "`available_tools` (every tool you can call — built-ins and MCP tools — as "
        "[{name, description}]); the planner only plans with tools you list."
    ),
}

CONSULT_DESC = {
    "heavy": (
        "REQUIRED in two situations: (1) when a step's preconditions don't hold, a "
        "referenced file is missing, a tool result is ambiguous, or you would need to "
        "make ANY judgment call not explicitly covered by the plan; (2) when you've "
        "uncovered MATERIAL INFORMATION that may change what the rest of the plan "
        "should do — a discovered SOP violation, an unsuspected recurring pattern, a "
        "finding that makes downstream steps redundant or wrong. Returns "
        "{proceed, revise, replan, skip, escalate}. `replan` returns a fresh set of "
        "remaining steps when the situation calls for redirecting the plan, not just "
        "tweaking one step. NO penalty for over-consulting; significant risk in "
        "under-consulting on either trigger."
    ),
    "light": (
        "Consult the planner mid-execution if a step fails OR if you find material "
        "information that may change the plan. Returns proceed/revise/replan/skip/escalate."
    ),
}

SYNTHESIZE_DESC = {
    "heavy": (
        "REQUIRED after plan execution and BEFORE generating any human-facing output. "
        "Takes the gathered evidence and produces a structured analytical synthesis — "
        "key findings, evidence summary, gaps. You are NOT authorized to write your "
        "own analysis; this tool does it. Call once per plan execution after all steps "
        "are complete (or after you have decided to stop executing). "
        "IMPORTANT — for any step result that is the contents of a FILE, pass "
        "{\"step_id\": N, \"file_path\": \"<absolute path>\"} and this tool reads the "
        "file itself. Do NOT paste large file contents inline — that truncates and "
        "corrupts. Use inline {\"step_id\": N, \"content\": \"...\"} only for non-file "
        "results (command output, web text, computed values). "
        "This tool may return EITHER a synthesis OR {\"status\": \"needs_more_info\", "
        "\"gather_steps\": [...], \"reason\": ...}. If it returns needs_more_info: run "
        "the gather_steps in order, then call synthesize AGAIN with the same "
        "session_id and ONLY the new step_results from those steps — the MCP retains "
        "the earlier evidence. Repeat until it returns a synthesis. The output feeds "
        "draft_output."
    ),
    "light": (
        "Produce a structured analytical synthesis after plan execution. For file-based "
        "step results pass {step_id, file_path} — the tool reads the file itself. "
        "Useful before drafting any human-facing output."
    ),
}

DRAFT_DESC = {
    "heavy": (
        "REQUIRED for any prose output intended for a human reader (notifications, "
        "CCIRs, memos, AAR sections, handover briefs). You are NOT authorized to draft "
        "these yourself — the staff writer (this tool) does it. Provide a purpose "
        "(safety_officer_notification, ccir, etc.) and an audience (battalion_cdr, "
        "safety_officer, etc.). Call AFTER synthesize. The returned text is the final "
        "draft to present to the user or write to a file — do not edit it without "
        "consulting again."
    ),
    "light": (
        "Generate a polished prose draft for a specific purpose and audience. "
        "Use after synthesize."
    ),
}

TRIAGE_DESC = {
    "heavy": (
        "REQUIRED as the FIRST tool call when a new incident report arrives if you "
        "do not yet know whether it warrants full planning. Returns a fast severity + "
        "summary classification. If the result has `needs_full_planner: true`, proceed "
        "to call get_plan. If false, you may handle routine items directly per local "
        "guidance. Cheaper and faster than get_plan — use this as the gate."
    ),
    "light": (
        "Lightweight classification of an incident report (severity, summary, whether "
        "full planning is warranted). Use as a fast pre-filter before get_plan."
    ),
}

if DESCRIPTION_STYLE not in GET_PLAN_DESC:
    print(
        f"[planner-mcp] WARNING: PLANNER_TOOL_STYLE={DESCRIPTION_STYLE!r} unrecognized; using 'heavy'",
        file=sys.stderr,
    )
    DESCRIPTION_STYLE = "heavy"

print(f"[planner-mcp] starting (tool-style={DESCRIPTION_STYLE})", file=sys.stderr)
for _tool, _model in MODELS.items():
    print(f"[planner-mcp]   {_tool}: {_model}", file=sys.stderr)
print(
    f"[planner-mcp]   synthesize info-requests: "
    f"{'enabled' if _INFO_REQUESTS_ENABLED else 'disabled'}",
    file=sys.stderr,
)

# ---- Session memory -------------------------------------------------------
# In-memory only — sessions die with the server process (per OpenCode run, or
# per interactive conversation). Sessions are deliberately small: they hold
# file PATHS, not file contents (see _resolve_step_result_files and
# _effective_input_text). So there is NO time-based expiry — context is never
# dropped out from under an in-progress task. A count cap is the only bound,
# guarding against unbounded growth in a very long-lived session.

_SESSIONS: dict[str, dict] = {}
_MAX_SESSIONS = 200  # keep the newest this many; drop the oldest beyond it


def _prune_sessions() -> None:
    """Drop the oldest sessions if we are holding more than the cap."""
    excess = len(_SESSIONS) - _MAX_SESSIONS
    if excess <= 0:
        return
    oldest = sorted(_SESSIONS, key=lambda sid: _SESSIONS[sid]["created_at"])[:excess]
    for sid in oldest:
        del _SESSIONS[sid]


def _new_session(
    user_intent: str,
    input_text: str,
    plan: dict,
    available_tools: list[dict] | None,
    input_files: list[str] | None = None,
) -> str:
    _prune_sessions()
    sid = secrets.token_hex(6)  # 12 hex chars; collision risk negligible at our scale
    _SESSIONS[sid] = {
        "user_intent": user_intent,
        "input_text": input_text,            # raw — file contents are NOT expanded into storage
        "input_files": input_files or [],    # paths only; contents read on demand
        "plan": plan,
        "available_tools": available_tools,
        "step_results": [],          # accumulates across synthesize rounds
        "synthesize_rounds": 0,      # how many times synthesize has run this session
        "created_at": time.time(),
    }
    return sid


def _get_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    return _SESSIONS.get(sid)


# ---- JSON extraction & validation -----------------------------------------


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
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


def _validate_plan(plan: dict, allowed_tools: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be a JSON object"]

    if not isinstance(plan.get("summary"), str) or not plan["summary"].strip():
        errors.append("summary must be a non-empty string")

    if not isinstance(plan.get("human_review_required"), bool):
        errors.append("human_review_required must be a boolean")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty array")
        return errors

    seen_ids: set[int] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{i}] must be an object")
            continue
        sid = step.get("id")
        if not isinstance(sid, int):
            errors.append(f"steps[{i}].id must be an integer")
        elif sid in seen_ids:
            errors.append(f"steps[{i}].id={sid} duplicates a prior step id")
        else:
            seen_ids.add(sid)

        tool = step.get("tool")
        if tool not in allowed_tools:
            errors.append(f"steps[{i}].tool={tool!r} must be one of {sorted(allowed_tools)}")

        if not isinstance(step.get("args"), dict):
            errors.append(f"steps[{i}].args must be an object")

        deps = step.get("depends_on", [])
        if not isinstance(deps, list):
            errors.append(f"steps[{i}].depends_on must be a list")
        else:
            for dep in deps:
                if not isinstance(dep, int):
                    errors.append(f"steps[{i}].depends_on contains non-int {dep!r}")
                elif dep not in seen_ids:
                    errors.append(f"steps[{i}].depends_on references step {dep} which is not defined before this step")

    return errors


def _validate_consult(reply: dict, allowed_tools: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(reply, dict):
        return ["consult response must be a JSON object"]

    decision = reply.get("decision")
    if decision not in ALLOWED_DECISIONS:
        errors.append(f"decision must be one of {sorted(ALLOWED_DECISIONS)}, got {decision!r}")

    if not isinstance(reply.get("reasoning"), str) or not reply["reasoning"].strip():
        errors.append("reasoning must be a non-empty string")

    revised = reply.get("revised_step")
    if decision == "revise":
        if not isinstance(revised, dict):
            errors.append("decision is 'revise' but revised_step is not an object")
        else:
            if revised.get("tool") not in allowed_tools:
                errors.append(f"revised_step.tool must be one of {sorted(allowed_tools)}")
            if not isinstance(revised.get("args"), dict):
                errors.append("revised_step.args must be an object")
    elif revised is not None:
        errors.append(f"revised_step must be null when decision is {decision!r}, got {type(revised).__name__}")

    remaining = reply.get("revised_remaining_steps")
    if decision == "replan":
        if not isinstance(remaining, list) or not remaining:
            errors.append("decision is 'replan' but revised_remaining_steps is not a non-empty list")
        else:
            for i, step in enumerate(remaining):
                if not isinstance(step, dict):
                    errors.append(f"revised_remaining_steps[{i}] must be an object")
                    continue
                if step.get("tool") not in allowed_tools:
                    errors.append(f"revised_remaining_steps[{i}].tool={step.get('tool')!r} must be one of {sorted(allowed_tools)}")
                if not isinstance(step.get("args"), dict):
                    errors.append(f"revised_remaining_steps[{i}].args must be an object")
            # Soft check: last step should be draft_output (mandatory final step)
            last = remaining[-1] if isinstance(remaining[-1], dict) else {}
            if last.get("tool") != DRAFT_OUTPUT_TOOL_NAME:
                errors.append(
                    f"revised_remaining_steps' last step should be {DRAFT_OUTPUT_TOOL_NAME!r} "
                    f"(every plan must end with draft_output); got {last.get('tool')!r}"
                )
    elif remaining is not None:
        errors.append(f"revised_remaining_steps must be null when decision is {decision!r}, got {type(remaining).__name__}")

    return errors


def _validate_synthesis(parsed: dict, allowed_tools: set[str], final_round: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(parsed, dict):
        return ["response must be a JSON object"]

    # Mode 2: a request for more information. Not permitted on the final round.
    if parsed.get("status") == "needs_more_info":
        if final_round:
            return [
                "this is the final synthesis round — output a synthesis, "
                "not a needs_more_info request"
            ]
        if not isinstance(parsed.get("reason"), str) or not parsed["reason"].strip():
            errors.append("needs_more_info.reason must be a non-empty string")
        steps = parsed.get("gather_steps")
        if not isinstance(steps, list) or not steps:
            errors.append("needs_more_info.gather_steps must be a non-empty array")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"gather_steps[{i}] must be an object")
                    continue
                tool = step.get("tool")
                if tool in (SYNTHESIZE_TOOL_NAME, DRAFT_OUTPUT_TOOL_NAME):
                    errors.append(
                        f"gather_steps[{i}].tool must not be synthesize or draft_output "
                        "— gather steps are discovery only"
                    )
                elif tool not in allowed_tools:
                    errors.append(
                        f"gather_steps[{i}].tool={tool!r} must be one of {sorted(allowed_tools)}"
                    )
                if not isinstance(step.get("args"), dict):
                    errors.append(f"gather_steps[{i}].args must be an object")
        return errors

    # Mode 1: a synthesis.
    findings = parsed.get("key_findings")
    if not isinstance(findings, list) or not findings:
        errors.append("key_findings must be a non-empty array")
    elif not all(isinstance(f, str) and f.strip() for f in findings):
        errors.append("all key_findings entries must be non-empty strings")

    if not isinstance(parsed.get("evidence_summary"), str) or len(parsed["evidence_summary"].strip()) < 100:
        errors.append("evidence_summary must be a substantive string (>=100 chars)")

    gaps = parsed.get("gaps_or_uncertainties")
    if not isinstance(gaps, list):
        errors.append("gaps_or_uncertainties must be an array (may be empty)")

    return errors


def _validate_triage(triage: dict, _allowed_tools: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(triage, dict):
        return ["triage must be a JSON object"]

    if triage.get("severity") not in ALLOWED_SEVERITY:
        errors.append(f"severity must be one of {sorted(ALLOWED_SEVERITY)}")
    if not isinstance(triage.get("summary"), str) or not triage["summary"].strip():
        errors.append("summary must be a non-empty string")
    if not isinstance(triage.get("human_review_required"), bool):
        errors.append("human_review_required must be a boolean")
    if not isinstance(triage.get("brief_rationale"), str) or not triage["brief_rationale"].strip():
        errors.append("brief_rationale must be a non-empty string")
    if not isinstance(triage.get("needs_full_planner"), bool):
        errors.append("needs_full_planner must be a boolean")

    return errors


# ---- genai.mil client -----------------------------------------------------


def _call_genai(messages: list[dict], model: str) -> tuple[str | None, str | None]:
    """Returns (content, error). Exactly one is non-None."""
    api_key = os.environ.get("GENAI_MIL_API_KEY")
    if not api_key:
        return None, "GENAI_MIL_API_KEY environment variable not set in the MCP server process"

    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.1},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        return None, f"network error talking to genai.mil: {e}"

    if resp.status_code != 200:
        return None, f"genai.mil returned HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        body = resp.json()
        return body["choices"][0]["message"]["content"], None
    except (KeyError, IndexError, ValueError) as e:
        return None, f"unexpected genai.mil response shape: {e}"


def _resolve_allowed_tools(available_tools: list[dict] | None) -> set[str]:
    """Extract just the names from a list of tool descriptors. Falls back to defaults.

    Always includes the planner-mcp's own synthesize and draft_output tool names
    because plans are required to end with calls to those tools.
    """
    tools = available_tools or DEFAULT_AVAILABLE_TOOLS
    names = {t["name"] for t in tools if isinstance(t, dict) and "name" in t}
    names.add(SYNTHESIZE_TOOL_NAME)
    names.add(DRAFT_OUTPUT_TOOL_NAME)
    return names


# Per-file read cap for server-side step-result resolution. Generous (Gemini's
# context is large) but bounds a pathological huge file.
_STEP_FILE_CHAR_CAP = 200_000


# Office/PDF formats store text compressed inside the container, so a plain
# byte read yields garbage — they must be parsed. The parsing libraries are
# optional: if one is missing, the reader returns a clear marker rather than
# crashing the MCP. Maps extension -> pip package name.
_DOC_PARSER_LIB = {
    ".pdf": "pypdf",
    ".docx": "python-docx",
    ".xlsx": "openpyxl",
    ".pptx": "python-pptx",
}


def _extract_document_text(path: str, ext: str) -> str:
    """Parse a binary office/PDF document into plain text.

    Raises ImportError if the format's parsing library is not installed.
    """
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        import docx
        doc = docx.Document(path)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f"# Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    if ext == ".pptx":
        import pptx
        pres = pptx.Presentation(path)
        parts = []
        for i, slide in enumerate(pres.slides, 1):
            parts.append(f"# Slide {i}")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        line = "".join(run.text for run in para.runs)
                        if line.strip():
                            parts.append(line)
        return "\n".join(parts)
    raise ValueError(f"no document extractor for {ext}")


def _read_file_capped(path: str) -> str:
    """Read a file server-side, size-capped, with a clear marker on failure.

    Office/PDF documents are parsed into text (the executor can pass a path
    to a .pdf/.docx/.xlsx/.pptx and the MCP extracts the readable content);
    everything else is read as UTF-8 text.
    """
    expanded = os.path.expanduser(path)
    ext = os.path.splitext(expanded)[1].lower()
    try:
        if ext in _DOC_PARSER_LIB:
            try:
                text = _extract_document_text(expanded, ext)
            except ImportError:
                lib = _DOC_PARSER_LIB[ext]
                print(f"[planner-mcp] cannot parse {ext} — '{lib}' not installed", file=sys.stderr)
                return (
                    f"[FILE NOT PARSED: {path} is a {ext} document; the MCP server "
                    f"needs the '{lib}' package to read it — pip install {lib}]"
                )
        else:
            with open(expanded, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
    except OSError as exc:
        print(f"[planner-mcp] could not read {path}: {exc}", file=sys.stderr)
        return f"[FILE NOT READ by MCP server: {path} — {exc}]"
    except Exception as exc:  # noqa: BLE001 — a malformed document must not crash the MCP
        print(f"[planner-mcp] could not parse {path}: {exc}", file=sys.stderr)
        return f"[FILE NOT PARSED by MCP server: {path} — {exc}]"

    if len(text) > _STEP_FILE_CHAR_CAP:
        text = text[:_STEP_FILE_CHAR_CAP] + "\n[...truncated by MCP server file-read cap...]"
    return text


def _resolve_step_result_files(step_results: list) -> list:
    """Read step_results entries that carry a `file_path`, server-side.

    The executor (a weak local model) is unreliable at ferrying large file
    contents into a tool call — it truncates and corrupts. When a step result
    carries a `file_path`, the MCP reads the file itself (it runs locally on
    the same machine) and substitutes the real, full content. A file that
    cannot be read becomes an explicit marker so synthesis flags it as a gap
    rather than crashing.
    """
    resolved = []
    for entry in step_results:
        if not isinstance(entry, dict) or not isinstance(entry.get("file_path"), str):
            resolved.append(entry)
            continue
        new_entry = dict(entry)
        new_entry["content"] = _read_file_capped(entry["file_path"])
        resolved.append(new_entry)
    return resolved


def _effective_input_text(input_text: str | None, input_files: list | None) -> str:
    """Combine raw input_text with the server-side-read contents of input_files.

    Sessions store input_files as PATHS only; their contents are expanded here
    at use time, so stored sessions stay small regardless of source-file size.
    """
    base = (input_text or "").strip()
    if not input_files:
        return base
    blocks = [f"--- FILE: {p} ---\n{_read_file_capped(str(p))}" for p in input_files]
    files_text = "\n\n".join(blocks)
    return f"{base}\n\n{files_text}" if base else files_text


def _call_with_validation(
    messages: list[dict],
    extractor: Callable[[str], dict | None],
    validator: Callable[[dict, set[str]], list[str]],
    kind: str,
    allowed_tools: set[str],
    model: str,
) -> dict:
    """Call genai, extract JSON, validate; one corrective retry on validation failure."""
    last_content = ""
    last_errors: list[str] = []

    for attempt in range(2):
        content, err = _call_genai(messages, model=model)
        if err:
            return {"error": err, "stage": "transport", "model": model}
        last_content = content or ""

        parsed = extractor(content or "")
        if parsed is None:
            if not RETRY_ON_VALIDATION_FAILURE or attempt == 1:
                return {
                    "error": "model did not return parseable JSON",
                    "stage": "parse",
                    "model": model,
                    "raw_preview": last_content[:500],
                }
            messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your last response was not parseable as JSON. Re-emit ONLY the "
                        f"{kind} as a pure JSON object: first character `{{`, last character "
                        "`}}`, no preamble, no markdown fences."
                    ),
                },
            ]
            continue

        errors = validator(parsed, allowed_tools)
        if not errors:
            return parsed

        last_errors = errors
        if not RETRY_ON_VALIDATION_FAILURE or attempt == 1:
            return {
                "error": "model output failed validation",
                "stage": "validate",
                "model": model,
                "validation_errors": errors,
                "raw_parsed": parsed,
            }

        messages = messages + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    f"Your last {kind} had these validation errors:\n- "
                    + "\n- ".join(errors)
                    + f"\n\nFix these and re-emit ONLY the corrected {kind} JSON. "
                    "First character `{{`, last character `}}`."
                ),
            },
        ]

    return {
        "error": "exhausted retries",
        "stage": "validate",
        "model": model,
        "validation_errors": last_errors,
    }


# ---- MCP server -----------------------------------------------------------

mcp = FastMCP("planner-mcp")


@mcp.tool(description=TRIAGE_DESC[DESCRIPTION_STYLE])
def triage_only(input_text: str) -> dict:
    """Fast severity + summary classification for incident-shaped reports.

    Only meaningful for incident-shaped tasks (safety events, operational issues
    with severity levels). For research, summarization, drafting, code generation
    or other tasks, skip triage and call get_plan directly.

    Args:
        input_text: Full text of the incident report to classify.

    Returns:
        JSON with severity, summary, human_review_required, brief_rationale,
        needs_full_planner. On failure, an object with an `error` key.
    """
    messages = build_triage_messages(input_text)
    return _call_with_validation(
        messages,
        _extract_json,
        _validate_triage,
        kind="triage classification",
        allowed_tools=set(),
        model=MODELS["triage_only"],
    )


@mcp.tool(description=GET_PLAN_DESC[DESCRIPTION_STYLE])
def get_plan(
    user_intent: str,
    available_tools: list[dict],
    input_text: str = "",
    input_files: list[str] | None = None,
) -> dict:
    """Generate an authoritative multi-step plan and open a session.

    The returned plan ALWAYS ends with two steps that call back into this MCP
    (synthesize, then draft_output). The executor just runs them in order — no
    special handling needed beyond passing session_id forward.

    Args:
        user_intent: REQUIRED. The user's actual request, passed verbatim from
            the executor's input. This is the planner's highest-fidelity signal
            for what kind of plan to produce. Examples:
              "produce a safety officer notification"
              "summarize this field manual for new soldiers"
              "find supporting docs and revise this CONOP"
              "explain what this code does"
            Pass the user's words faithfully — do NOT summarize, paraphrase,
            or try to derive a "category" from them.
        available_tools: REQUIRED. The full list of tools you (the executor)
            have access to — every built-in AND every MCP tool. Each entry is
            {"name": "<exact tool name>", "description": "<what it does, plus
            its argument names and types>"}. The planner builds steps ONLY
            from tools listed here; omitting a tool (e.g. a PDF reader) means
            the plan can never use it. Cached in the session and reused by
            consult_planner.
        input_text: Optional — the data the user is asking you to process
            (a report, document, prompt, code excerpt, etc.). May be empty if
            the task is open-ended and the user_intent is the entire context.
        input_files: Optional list of file PATHS. The MCP reads each file
            server-side and folds its contents into the planner's context.
            Prefer this over pasting large file contents into input_text —
            the session stores only the paths, so it stays small.

    Returns:
        The plan JSON with an additional `session_id` field. Save the
        session_id and pass it to consult_planner, synthesize, draft_output
        as you execute the plan steps.
    """
    if not user_intent or not user_intent.strip():
        return {"error": "user_intent is required and must be a non-empty string", "stage": "input"}

    if not isinstance(available_tools, list) or not available_tools:
        return {
            "error": (
                "available_tools is required: pass the full list of tools you "
                "have access to — built-ins AND every MCP tool — as a non-empty "
                'list of {"name": str, "description": str} objects.'
            ),
            "stage": "input",
        }
    malformed = [
        t for t in available_tools
        if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t["name"].strip()
    ]
    if malformed:
        return {
            "error": (
                f"{len(malformed)} available_tools entr"
                f"{'y is' if len(malformed) == 1 else 'ies are'} malformed: each "
                'entry must be an object with a non-empty string "name" (and '
                'ideally a "description" covering the tool\'s arguments).'
            ),
            "stage": "input",
        }

    if input_files is not None and not isinstance(input_files, list):
        return {"error": "input_files, when provided, must be a list of file paths", "stage": "input"}

    allowed_tools = _resolve_allowed_tools(available_tools)
    effective_input = _effective_input_text(input_text, input_files)
    messages = build_messages(user_intent, effective_input, available_tools)
    result = _call_with_validation(
        messages,
        _extract_json,
        _validate_plan,
        kind="plan",
        allowed_tools=allowed_tools,
        model=MODELS["get_plan"],
    )

    if "error" not in result:
        # Store raw input_text + input_files (paths) — not the expanded text —
        # so the session stays small. Consumers re-expand via _effective_input_text.
        sid = _new_session(user_intent, input_text, result, available_tools, input_files)
        result["session_id"] = sid

    return result


@mcp.tool(description=CONSULT_DESC[DESCRIPTION_STYLE])
def consult_planner(
    current_step: dict,
    problem: str,
    session_id: str | None = None,
    user_intent: str | None = None,
    input_text: str | None = None,
    available_tools: list[dict] | None = None,
) -> dict:
    """Consult the planner mid-execution when something needs review.

    Call this in two situations:
    (1) A step failed or its preconditions don't hold (file missing, ambiguous
        result, permission denied, etc.).
    (2) You uncovered material information that may change the rest of the
        plan (a discovered violation, an unsuspected pattern, a finding that
        makes downstream steps wrong or redundant).

    Args:
        current_step: The step object the executor is currently working on.
        problem: Description of what went wrong, what's ambiguous, OR what
            material finding suggests the plan needs revision. Be specific.
        session_id: If provided, user_intent, input_text, and available_tools
            are pulled from session memory.
        user_intent: Required if session_id is not provided.
        input_text: Required if session_id is not provided.
        available_tools: Optional; pulled from session if session_id is given.

    Returns:
        JSON with decision (proceed|revise|replan|skip|escalate), reasoning,
        and either revised_step (for "revise") or revised_remaining_steps
        (for "replan") as appropriate.
    """
    session = _get_session(session_id)
    if session:
        user_intent = user_intent or session["user_intent"]
        if input_text is None:
            input_text = _effective_input_text(session["input_text"], session.get("input_files"))
        available_tools = available_tools or session["available_tools"]
    elif not user_intent or input_text is None:
        return {"error": "must provide either session_id or both user_intent and input_text", "stage": "input"}

    allowed_tools = _resolve_allowed_tools(available_tools)
    messages = build_consult_messages(user_intent, input_text, current_step, problem)
    return _call_with_validation(
        messages,
        _extract_json,
        _validate_consult,
        kind="consult response",
        allowed_tools=allowed_tools,
        model=MODELS["consult_planner"],
    )


@mcp.tool(description=SYNTHESIZE_DESC[DESCRIPTION_STYLE])
def synthesize(
    step_results: list[dict],
    session_id: str | None = None,
    user_intent: str | None = None,
    input_text: str | None = None,
    plan: dict | None = None,
) -> dict:
    """Produce a structured analytical synthesis after plan execution.

    Args:
        step_results: List of executed-step results. For a result that is the
            contents of a file, pass {"step_id": N, "intent": "...",
            "file_path": "<absolute path>"} — the MCP reads the file itself,
            avoiding the executor truncating or corrupting large content. For
            non-file results (command output, web text, computed values) pass
            inline {"step_id": N, "content": "..."}.
        session_id: Optional session_id from get_plan; if provided, user_intent,
            input_text, and plan are pulled from session memory.
        user_intent: Required if session_id is not provided.
        input_text: Required if session_id is not provided.
        plan: Required if session_id is not provided.

    Returns:
        Either a synthesis (key_findings, evidence_summary,
        gaps_or_uncertainties) OR a {"status": "needs_more_info",
        "gather_steps": [...], "reason": ...} request — in which case run the
        gather_steps and call synthesize again with the new step_results. The
        session accumulates step_results across rounds; the final round is
        forced to produce a synthesis.
    """
    session = _get_session(session_id)
    if session:
        user_intent = user_intent or session["user_intent"]
        if input_text is None:
            input_text = _effective_input_text(session["input_text"], session.get("input_files"))
        plan = plan or session["plan"]
        available_tools = session.get("available_tools")
    elif not user_intent or input_text is None or plan is None:
        return {"error": "must provide either session_id or all of user_intent, input_text, and plan", "stage": "input"}
    else:
        available_tools = None

    if not isinstance(step_results, list):
        return {"error": "step_results must be a list", "stage": "input"}

    # Accumulate evidence across rounds. The executor passes only the NEW
    # step_results each round; the session retains everything gathered so far,
    # so synthesize always sees the full picture. needs_more_info requests
    # require a session — without one, force a single final round.
    if session is not None:
        accumulated = session.setdefault("step_results", [])
        accumulated.extend(step_results)
        all_results = accumulated
        session["synthesize_rounds"] = session.get("synthesize_rounds", 0) + 1
        round_num = session["synthesize_rounds"]
    else:
        all_results = step_results
        round_num = MAX_SYNTHESIZE_ROUNDS  # no session: force a final synthesis

    # The last round forces a synthesis; so does disabling info-requests entirely.
    final_round = round_num >= MAX_SYNTHESIZE_ROUNDS or not _INFO_REQUESTS_ENABLED

    # Read any file_path-bearing entries server-side — the executor is
    # unreliable at ferrying large file contents (it truncates and corrupts).
    resolved = _resolve_step_result_files(all_results)
    allowed_tools = _resolve_allowed_tools(available_tools)

    messages = build_synthesize_messages(
        user_intent, input_text, plan, resolved,
        round_num=round_num, max_rounds=MAX_SYNTHESIZE_ROUNDS,
    )
    result = _call_with_validation(
        messages,
        _extract_json,
        lambda parsed, tools: _validate_synthesis(parsed, tools, final_round=final_round),
        kind="synthesis",
        allowed_tools=allowed_tools,
        model=MODELS["synthesize"],
    )
    if isinstance(result, dict) and result.get("status") == "needs_more_info":
        result["session_id"] = session_id
    return result


@mcp.tool(description=DRAFT_DESC[DESCRIPTION_STYLE])
def draft_output(
    purpose: str,
    audience: str,
    synthesis: dict,
    session_id: str | None = None,
    user_intent: str | None = None,
    input_text: str | None = None,
    extra_guidance: str = "",
) -> dict:
    """Generate a polished prose draft for a specific purpose and audience.

    Args:
        purpose: What kind of artifact ("safety_officer_notification",
            "field_manual_summary", "conop_revision", "executive_brief",
            "code_explanation", etc — derived from the user's intent).
        audience: Intended reader ("battalion_safety_officer",
            "originating_planner", "new_soldiers", etc).
        synthesis: The synthesis object from synthesize() — provides facts
            and analysis.
        session_id: Optional session_id from get_plan; if provided,
            user_intent and input_text are pulled from session memory.
        user_intent: Required if session_id is not provided.
        input_text: Required if session_id is not provided.
        extra_guidance: Optional additional guidance for the writer (e.g.
            "keep under 200 words", "include grid coordinates", "BLUF format").

    Returns:
        {"draft_text": "<the draft>", "model": "...", "purpose": "...", "audience": "..."}.
    """
    session = _get_session(session_id)
    if session:
        user_intent = user_intent or session["user_intent"]
        input_text = input_text if input_text is not None else session["input_text"]
    elif not user_intent or input_text is None:
        return {"error": "must provide either session_id or both user_intent and input_text", "stage": "input"}

    if not isinstance(synthesis, dict) or "error" in synthesis:
        return {"error": "synthesis must be a valid synthesis object (from synthesize())", "stage": "input"}

    messages = build_draft_messages(purpose, audience, user_intent, input_text, synthesis, extra_guidance)
    content, err = _call_genai(messages, model=MODELS["draft_output"])
    if err:
        return {"error": err, "stage": "transport", "model": MODELS["draft_output"]}

    draft = (content or "").strip()
    if len(draft) < 50:
        return {
            "error": "draft is suspiciously short",
            "stage": "validate",
            "model": MODELS["draft_output"],
            "draft_preview": draft,
        }

    return {
        "draft_text": draft,
        "model": MODELS["draft_output"],
        "purpose": purpose,
        "audience": audience,
    }


if __name__ == "__main__":
    mcp.run()
