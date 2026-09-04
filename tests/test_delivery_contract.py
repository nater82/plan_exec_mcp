"""Offline contract tests for draft_output's delivery signalling.

No API key, no network: _draft_with_validation is stubbed so only the
return-shape logic is exercised.

Regression origin (2026-08-20): in the staff-MCP benchmark, hybrid-v3
oporder/v2 called draft_output WITHOUT save_to_path, got a complete memo
back in draft_text, wrote nothing, and then told the user "The compliance
memo has been written to ...". The cell scored 0 for non-delivery even
though the content was good. draft_output must make a non-save
unmistakable so the executor cannot mistake drafting for delivery.
"""

import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import server  # noqa: E402

SYNTH = {"key_findings": [{"claim": "x" * 30, "sources": ["step:1"]}]}
DRAFT = "MEMORANDUM FOR Command Staff\n\n" + ("Substantive body text. " * 20)

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def call(**kw) -> dict:
    return server.draft_output(
        purpose="compliance_memo",
        audience="command_staff",
        synthesis=SYNTH,
        user_intent="Produce a compliance memo.",
        input_text="SOP and CONOP text.",
        **kw,
    )


def main() -> int:
    server._draft_with_validation = lambda messages, save_to_path, *a, **k: (DRAFT, None)

    print("\n=== no save_to_path: must announce that nothing was written ===")
    out = call()
    check(out.get("draft_text") == DRAFT, "draft_text still returned")
    check(out.get("saved") is False, "saved is False (explicit, not absent)")
    warn = out.get("delivery_warning", "")
    check(bool(warn), "delivery_warning present")
    check("NO FILE WAS WRITTEN" in warn.upper(), "warning states no file was written")
    check("save_to_path" in warn, "warning names save_to_path as the remedy")

    print("\n=== with save_to_path: must confirm the real write ===")
    with tempfile.TemporaryDirectory() as td:
        p = str(Path(td) / "nested" / "compliance_memo.md")
        out = call(save_to_path=p)
        check(out.get("saved") is True, "saved is True")
        # Compare resolved paths, not raw strings: on Windows a temp dir may come
        # back as an 8.3 short path (NATHAN~1.ROL) that .resolve() legitimately
        # expands, so string equality fails even though the write is correct.
        same = bool(out.get("saved_to")) and \
            Path(out["saved_to"]).resolve() == Path(p).resolve()
        check(same, "saved_to points at the requested file")
        check("delivery_warning" not in out, "no delivery_warning on a real save")
        check(Path(p).exists(), "file actually exists on disk")
        check(Path(p).read_text() == DRAFT, "file content == draft_text")

    print(f"\n{'=' * 60}")
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
