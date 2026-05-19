# Getting started, from nothing to working

This is the step-by-step. If you want to understand *what* this repo does
or *how* it works, read [README.md](README.md) first. If you just want it
running, follow the steps below.

## Before you start, you need

- A working terminal: WSL Ubuntu on Windows, or Terminal on macOS, or any
  Linux terminal. **If you're on Windows and don't have WSL yet**, follow
  [docs/WSL_SETUP.md](docs/WSL_SETUP.md) first, then come back here.
- An API key for `https://api.genai.mil`. Your office should have a
  process for issuing these — ask whoever sent you this repo.
- About 15 minutes the first time you set it up.

## What you'll end up with

- A local clone of this repo at a path of your choosing.
- A working Python virtualenv with the MCP server installed.
- A local `opencode.json` and `AGENTS.md` configured for your machine.
- OpenCode installed and able to call the MCP, which calls Gemini, which
  thinks for you while OpenCode does the local work.

---

## Step 1. Clone the repo

In your terminal:

```sh
cd ~
git clone <REPO_URL>          # placeholder — get this from the repo maintainer
cd <REPO_DIR>                 # placeholder — the folder name git created
```

> **Placeholders:** Replace `<REPO_URL>` with the git URL (e.g.
> `git@github.com:<org>/<repo>.git`) and `<REPO_DIR>` with the folder name
> it cloned into (e.g. `plan_exec_mcp`). Your office should have shared the
> exact values.

## Step 2. Run the setup script

```sh
python3 scripts/setup.py
```

This is interactive — it asks before each significant step. It will:

1. Create a Python virtualenv at `.venv/`
2. Install the MCP server's dependencies
3. Generate a working `opencode.json` from the template (with your repo path)
4. Copy `AGENTS.example.md` to `AGENTS.md`
5. Run a healthcheck against the genai.mil endpoint

If step 5 says `GENAI_MIL_API_KEY is NOT set`, do step 3 below and re-run
the script.

## Step 3. Set your API key (one time, persistent)

```sh
echo 'export GENAI_MIL_API_KEY=your-key-here' >> ~/.bashrc
source ~/.bashrc
```

Replace `your-key-here` with your actual key. **Do NOT put the key in any
file inside this repo.** `~/.bashrc` is the right place — it's loaded
every time you open a terminal.

Verify it took:

```sh
echo "${GENAI_MIL_API_KEY:0:8}..."   # should print the first 8 chars of your key
```

Then re-run the setup script from step 2 — it'll skip the things it already
did and just run the healthcheck.

## Step 4. Install OpenCode (one time, global)

If you don't already have OpenCode installed:

```sh
npm install -g opencode-ai
opencode --version
```

(If `npm` isn't installed, see [docs/WSL_SETUP.md](docs/WSL_SETUP.md) Step 3
for the Node.js install.)

## Step 5. Wire the providers into OpenCode (one time, global)

OpenCode needs to know how to talk to the genai.mil endpoint (for the
planner-mcp's brain) and your on-prem/local executor models (for the
local tool execution). Copy our provider template into your OpenCode
global config — then edit the placeholder URLs in the provider template
to point at the actual endpoints your org provides:

```sh
mkdir -p ~/.config/opencode
cp config/providers.example.json ~/.config/opencode/opencode.json
```

If you already have a `~/.config/opencode/opencode.json` you don't want to
overwrite, open both files in an editor and merge the `provider` blocks
manually.

## Step 6. Try it

```sh
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at tests/test_report.txt and produce a safety-officer notification."
```

Or a non-incident task — the MCP works for any research/synthesis/drafting task:

```sh
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Read AGENTS.md and server.py and produce a one-page architectural overview for a new contributor."
```

This will take about 2-3 minutes. You should see:

- OpenCode launching with the executor model.
- A `planner-mcp-heavy_*` tool call (the executor reaching into the MCP).
- Some tool execution (Read, Grep, etc.).
- A final notification in your terminal.

If it works, you're done with setup. From now on you can use any model in
the `providers.example.json` list and any prompt.

## What to do if something breaks

| Symptom | Likely fix |
|---|---|
| `GENAI_MIL_API_KEY` not set | Did Step 3, opened a new terminal. |
| Healthcheck says `401 unauthorized` | Your key is locked. Visit the URL the error provides, or contact whoever issued the key. |
| Healthcheck says `404 not found` for a model | A model name has changed. Edit `server.py`'s `_TOOL_MODEL_DEFAULTS`, or override via the `PLANNER_MODEL_*` env vars. |
| `opencode: command not found` | Step 4 didn't complete. Re-run, check for npm permission errors. |
| `opencode run` says model not found | Did Step 5. Restart your terminal so `opencode` picks up the new config. |
| OpenCode runs but doesn't use the MCP | Check that `opencode.json` is in the working directory you're running `opencode` from. The setup script puts it at the repo root. |
| MCP runs but Gemini calls time out | Network — confirm you can reach `https://api.genai.mil` from this terminal: `curl -I https://api.genai.mil/v1/models`. |

If you're stuck, run the healthcheck explicitly and paste the output to
whoever's helping:

```sh
.venv/bin/python scripts/healthcheck.py
```

## What to read next

- [README.md](README.md) — what this is, how it works, the design notes
- [config/README.md](config/README.md) — config file reference, advanced setup
- [tests/README.md](tests/README.md) — how to validate changes
