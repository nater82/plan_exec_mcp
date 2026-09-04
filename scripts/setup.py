"""Interactive setup for this repo.

Run from the repo root:

    python3 scripts/setup.py

Does the following, prompting before each significant step:

  1. Creates a Python virtualenv at .venv/
  2. Installs the MCP server's dependencies (mcp, requests)
  3. Registers the planner-mcp in OpenCode's GLOBAL config
     (~/.config/opencode/opencode.json) so it loads from any directory
  4. Optionally adds the example provider blocks to that same global
     config (only ones you don't already have; never overwrites)
  5. Copies config/AGENTS.example.md to AGENTS.md
  6. Runs scripts/healthcheck.py to verify the genai.mil endpoint works

Skip steps you've already done — the script detects existing files and
asks before overwriting.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"

# Python's venv layout is platform-dependent: Windows puts executables in
# Scripts/ with .exe suffixes, POSIX puts them in bin/. Everything below goes
# through these helpers so a native-Windows install works without WSL.
IS_WINDOWS = os.name == "nt"
VENV_BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
EXE = ".exe" if IS_WINDOWS else ""


def venv_python() -> Path:
    return VENV_BIN / f"python{EXE}"


def venv_pip() -> Path:
    return VENV_BIN / f"pip{EXE}"


def venv_python_display() -> str:
    """Path as a user should type it, for printed instructions."""
    return f".venv\\Scripts\\python{EXE}" if IS_WINDOWS else ".venv/bin/python"
REQUIREMENTS = REPO_ROOT / "requirements.txt"

OPENCODE_TEMPLATE = REPO_ROOT / "config" / "opencode.example.json"
PROVIDERS_TEMPLATE = REPO_ROOT / "config" / "providers.example.json"
GLOBAL_OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
GLOBAL_CONFIG_BACKUP = GLOBAL_OPENCODE_CONFIG.with_name("opencode.json.bak")

AGENTS_TEMPLATE = REPO_ROOT / "config" / "AGENTS.example.md"
AGENTS_LOCAL = REPO_ROOT / "AGENTS.md"

HEALTHCHECK_SCRIPT = REPO_ROOT / "scripts" / "healthcheck.py"

PLACEHOLDER = "__GENAI_MCP_DIR__"
PYTHON_PLACEHOLDER = "__GENAI_MCP_PYTHON__"


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


def _backup_global_config() -> None:
    """Back up the global OpenCode config once, before setup first modifies it."""
    if GLOBAL_OPENCODE_CONFIG.exists() and not GLOBAL_CONFIG_BACKUP.exists():
        GLOBAL_CONFIG_BACKUP.write_text(GLOBAL_OPENCODE_CONFIG.read_text())
        ok(f"backed up existing config -> {GLOBAL_CONFIG_BACKUP}")


def _load_global_config() -> dict | None:
    """Load the global config as a dict (fresh skeleton if absent).

    Returns None if the file exists but is not valid JSON.
    """
    if not GLOBAL_OPENCODE_CONFIG.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    try:
        return json.loads(GLOBAL_OPENCODE_CONFIG.read_text())
    except json.JSONDecodeError as exc:
        err(f"existing {GLOBAL_OPENCODE_CONFIG} is not valid JSON: {exc}")
        print("    Fix or remove that file, then re-run setup.")
        return None


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
    pip = venv_pip()
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


def step_register_mcp() -> bool:
    header("Step 3: Register the planner-mcp in OpenCode's global config")
    if not OPENCODE_TEMPLATE.exists():
        err(f"template not found: {OPENCODE_TEMPLATE}")
        return False

    # as_posix() on purpose: a Windows path like C:\\Users\\x would be substituted
    # into JSON *text* before parsing, where the backslashes are invalid escapes
    # and json.loads() fails. Forward slashes are accepted by Windows Python.
    template = json.loads(
        OPENCODE_TEMPLATE.read_text()
        .replace(PYTHON_PLACEHOLDER, venv_python().as_posix())
        .replace(PLACEHOLDER, REPO_ROOT.as_posix())
    )
    mcp_blocks = template.get("mcp", {})
    if not mcp_blocks:
        err("template config/opencode.example.json has no 'mcp' block")
        return False

    print(f"  Registering the MCP in your GLOBAL OpenCode config:")
    print(f"    {GLOBAL_OPENCODE_CONFIG}")
    print("  This makes the planner-mcp load in every OpenCode session, from any")
    print("  directory. A repo-local opencode.json would only load when OpenCode")
    print("  runs from the repo folder itself — a common and confusing footgun.")

    if not ask_yes_no("Register the MCP globally?", default=True):
        warn("skipped. To register by hand later, merge the 'mcp' block from")
        print(f"    config/opencode.example.json into {GLOBAL_OPENCODE_CONFIG}")
        print(f"    (replacing {PLACEHOLDER} with {REPO_ROOT.as_posix()}).")
        return True

    GLOBAL_OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _backup_global_config()
    existing = _load_global_config()
    if existing is None:
        return False

    existing.setdefault("mcp", {})
    for name, block in mcp_blocks.items():
        if name in existing["mcp"]:
            warn(f"'mcp.{name}' already registered — refreshing it with current paths")
        existing["mcp"][name] = block

    GLOBAL_OPENCODE_CONFIG.write_text(json.dumps(existing, indent=2) + "\n")
    ok(f"registered [{', '.join(mcp_blocks)}] in {GLOBAL_OPENCODE_CONFIG}")
    print("  Restart OpenCode if it's running — the MCP block is read at startup.")
    return True


def step_providers() -> bool:
    header("Step 4: Add executor provider blocks to the global config")
    if not PROVIDERS_TEMPLATE.exists():
        err(f"template not found: {PROVIDERS_TEMPLATE}")
        return False

    provider_blocks = json.loads(PROVIDERS_TEMPLATE.read_text()).get("provider", {})
    if not provider_blocks:
        err("config/providers.example.json has no 'provider' block")
        return False

    print("  OpenCode needs provider blocks for the executor models it runs on")
    print("  your machine. This step can add the example providers")
    print(f"  ({', '.join(provider_blocks)}) to your global config.")
    print("  SAFE MERGE: it only adds providers you don't already have — it never")
    print("  overwrites an existing provider block, so your real endpoint URLs and")
    print("  any providers you've already configured are left untouched.")
    print("  The blocks it adds use PLACEHOLDER URLs you must edit afterward.")

    if not ask_yes_no("Add the example provider blocks now?", default=True):
        warn("skipped. Add them yourself: merge the 'provider' block from")
        print(f"    config/providers.example.json into {GLOBAL_OPENCODE_CONFIG}")
        print("    (keep the existing 'mcp' block and any providers you already have).")
        return True

    GLOBAL_OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _backup_global_config()
    existing = _load_global_config()
    if existing is None:
        return False

    existing.setdefault("provider", {})
    added, skipped = [], []
    for name, block in provider_blocks.items():
        if name in existing["provider"]:
            skipped.append(name)
        else:
            existing["provider"][name] = block
            added.append(name)

    GLOBAL_OPENCODE_CONFIG.write_text(json.dumps(existing, indent=2) + "\n")
    if skipped:
        warn(f"left your existing provider(s) untouched: {', '.join(skipped)}")
    if added:
        ok(f"added provider(s): {', '.join(added)}")
        print("  IMPORTANT: before running OpenCode, edit the placeholder endpoint")
        print(f"  URLs for the added provider(s) in {GLOBAL_OPENCODE_CONFIG}.")
        print("  (The genai-mil provider is optional — see config/README.md.)")
    else:
        ok("all example providers already present — nothing to add")
    return True


def step_agents_md() -> bool:
    header("Step 5: AGENTS.md (optional executor system prompt)")
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
    header("Step 6: Healthcheck against genai.mil")
    if not os.environ.get("GENAI_MIL_API_KEY"):
        warn("GENAI_MIL_API_KEY is not set in this shell.")
        print("    Set it now (export GENAI_MIL_API_KEY=...) and re-run this step manually:")
        print(f"      {venv_python_display()} {HEALTHCHECK_SCRIPT.relative_to(REPO_ROOT)}")
        print("    Or add it to your shell rc file:")
        print("      echo 'export GENAI_MIL_API_KEY=your-key' >> ~/.bashrc && source ~/.bashrc")
        return True  # not a hard failure; user just needs to set the key

    python = venv_python()
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
    print("  Edit your provider endpoint URLs:")
    print("    If setup added the provider blocks (step 4), open the global config")
    print(f"    {GLOBAL_OPENCODE_CONFIG}")
    print("    and replace the placeholder URLs for org-gptoss / org-gemma with")
    print("    your real executor endpoints. See config/README.md for details.")
    print()
    print("  Run the MCP smoke test (~2-3 min):")
    print(f"    {venv_python_display()} tests/test_server_logic.py")
    print()
    print("  Try a real end-to-end run via OpenCode. The --model you pass is the")
    print("  EXECUTOR — it must be a local/on-prem model, never a genai-mil/gemini")
    print("  model (Gemini runs remotely and cannot touch your local files):")
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
    # Line-buffer stdout so our prints stay correctly ordered with subprocess
    # output even when output is piped or redirected (not a TTY).
    sys.stdout.reconfigure(line_buffering=True)

    print(f"{BOLD}genai_mcp setup{RESET}")
    print(f"repo root: {REPO_ROOT}")

    steps = [
        ("venv", step_venv),
        ("deps", step_install_deps),
        ("register-mcp", step_register_mcp),
        ("providers", step_providers),
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
