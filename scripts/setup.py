"""Interactive setup for this repo.

Run from the repo root:

    python3 scripts/setup.py

Does the following, prompting before each significant step:

  1. Creates a Python virtualenv at .venv/
  2. Installs the MCP server's dependencies (mcp, requests)
  3. Generates a working opencode.json from config/opencode.example.json
     with the absolute path to this repo substituted in
  4. Copies config/AGENTS.example.md to AGENTS.md
  5. Runs scripts/healthcheck.py to verify the genai.mil endpoint works

Skip steps you've already done — the script detects existing files and
asks before overwriting.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.txt"

OPENCODE_TEMPLATE = REPO_ROOT / "config" / "opencode.example.json"
OPENCODE_LOCAL = REPO_ROOT / "opencode.json"

AGENTS_TEMPLATE = REPO_ROOT / "config" / "AGENTS.example.md"
AGENTS_LOCAL = REPO_ROOT / "AGENTS.md"

HEALTHCHECK_SCRIPT = REPO_ROOT / "scripts" / "healthcheck.py"

PLACEHOLDER = "__GENAI_MCP_DIR__"


# ---- helpers --------------------------------------------------------------

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(text: str) -> None:
    print(f"\n{BOLD}== {text} =={RESET}")


def ok(text: str) -> None:
    print(f"  {GREEN}✔{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}!{RESET} {text}")


def err(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Yes/No prompt. Defaults to `default` on empty input."""
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        reply = input(prompt + suffix).strip().lower()
        if not reply:
            return default
        if reply in ("y", "yes"):
            return True
        if reply in ("n", "no"):
            return False
        print("  Please answer y or n.")


# ---- steps ----------------------------------------------------------------


def step_venv() -> bool:
    header("Step 1: Python virtualenv")
    if VENV_DIR.exists():
        ok(f".venv/ already exists at {VENV_DIR}")
        if not ask_yes_no("Recreate it?", default=False):
            return True
        shutil.rmtree(VENV_DIR)

    print(f"  Creating venv at {VENV_DIR}...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0:
        err("venv creation failed. You may need `apt install python3-venv` (on Debian/Ubuntu).")
        return False
    ok("venv created")
    return True


def step_install_deps() -> bool:
    header("Step 2: Install dependencies")
    pip = VENV_DIR / "bin" / "pip"
    if not pip.exists():
        err(f"venv pip not found at {pip}. Re-run step 1.")
        return False

    print("  Installing requirements (mcp, requests)...")
    result = subprocess.run(
        [str(pip), "install", "--quiet", "-r", str(REQUIREMENTS)],
    )
    if result.returncode != 0:
        err("pip install failed. Check error output above.")
        return False
    ok("dependencies installed")
    return True


def step_opencode_json() -> bool:
    header("Step 3: Generate local opencode.json")
    if not OPENCODE_TEMPLATE.exists():
        err(f"template not found: {OPENCODE_TEMPLATE}")
        return False

    if OPENCODE_LOCAL.exists():
        warn(f"opencode.json already exists at {OPENCODE_LOCAL}")
        if not ask_yes_no("Overwrite with a fresh copy from the template?", default=False):
            ok("keeping existing opencode.json")
            return True

    content = OPENCODE_TEMPLATE.read_text().replace(PLACEHOLDER, str(REPO_ROOT))
    OPENCODE_LOCAL.write_text(content)
    ok(f"wrote {OPENCODE_LOCAL}")
    return True


def step_agents_md() -> bool:
    header("Step 4: AGENTS.md (optional executor system prompt)")
    if not AGENTS_TEMPLATE.exists():
        err(f"template not found: {AGENTS_TEMPLATE}")
        return False

    print("  The MCP is self-contained — it works without AGENTS.md.")
    print("  AGENTS.md adds executor-side steering that improves robustness when")
    print("  plan steps fail (e.g. referenced files missing). Recommended for")
    print("  production use with weaker executors (Gemma); optional otherwise.")

    if AGENTS_LOCAL.exists():
        warn(f"AGENTS.md already exists at {AGENTS_LOCAL}")
        if not ask_yes_no("Overwrite with a fresh copy from the template?", default=False):
            ok("keeping existing AGENTS.md")
            return True
        shutil.copy2(AGENTS_TEMPLATE, AGENTS_LOCAL)
        ok(f"wrote {AGENTS_LOCAL}")
        return True

    if not ask_yes_no("Install AGENTS.md from the template?", default=True):
        ok("skipping AGENTS.md (you can copy config/AGENTS.example.md manually later)")
        return True

    shutil.copy2(AGENTS_TEMPLATE, AGENTS_LOCAL)
    ok(f"wrote {AGENTS_LOCAL}")
    return True


def step_healthcheck() -> bool:
    header("Step 5: Healthcheck against genai.mil")
    if not os.environ.get("GENAI_MIL_API_KEY"):
        warn("GENAI_MIL_API_KEY is not set in this shell.")
        print("    Set it now (export GENAI_MIL_API_KEY=...) and re-run this step manually:")
        print(f"      .venv/bin/python {HEALTHCHECK_SCRIPT.relative_to(REPO_ROOT)}")
        print("    Or add it to your shell rc file:")
        print("      echo 'export GENAI_MIL_API_KEY=your-key' >> ~/.bashrc && source ~/.bashrc")
        return True  # not a hard failure; user just needs to set the key

    python = VENV_DIR / "bin" / "python"
    if not python.exists():
        err(f"venv python not found at {python}. Re-run step 1.")
        return False

    print("  Running healthcheck (this calls genai.mil once per configured model)...")
    result = subprocess.run([str(python), str(HEALTHCHECK_SCRIPT)])
    if result.returncode == 0:
        ok("healthcheck passed")
        return True
    err("healthcheck failed. See output above for which check(s) failed.")
    return False


def print_next_steps() -> None:
    header("Next steps")
    print()
    print("  Set your API key if you haven't already:")
    print("    echo 'export GENAI_MIL_API_KEY=your-key' >> ~/.bashrc && source ~/.bashrc")
    print()
    print("  Wire the providers into OpenCode (one-time, global):")
    print(f"    cp config/providers.example.json ~/.config/opencode/opencode.json")
    print("    (or merge into your existing ~/.config/opencode/opencode.json)")
    print()
    print("  Run the MCP smoke test (~2-3 min):")
    print("    .venv/bin/python tests/test_server_logic.py")
    print()
    print("  Try a real end-to-end run via OpenCode:")
    print("    opencode run --model org-gptoss/openai/gpt-oss-120b \\")
    print("      \"Process the incident report at tests/test_report.txt \\")
    print("       and produce a safety-officer notification.\"")
    print()
    print("  Or any research/synthesis/drafting task:")
    print("    opencode run --model org-gptoss/openai/gpt-oss-120b \\")
    print("      \"Read AGENTS.md and server.py and produce a one-page \\")
    print("       architectural overview for a new contributor.\"")
    print()


def main() -> int:
    print(f"{BOLD}plan_exec_mcp setup{RESET}")
    print(f"repo root: {REPO_ROOT}")

    steps = [
        ("venv", step_venv),
        ("deps", step_install_deps),
        ("opencode.json", step_opencode_json),
        ("AGENTS.md", step_agents_md),
        ("healthcheck", step_healthcheck),
    ]

    for name, step_fn in steps:
        if not step_fn():
            err(f"step {name!r} failed. Fix the issue above and re-run this script.")
            return 1

    print_next_steps()
    return 0


if __name__ == "__main__":
    sys.exit(main())
