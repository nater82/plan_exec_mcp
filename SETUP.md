# Getting started, from nothing to working

This is the step-by-step. If you want to understand *what* this repo does
or *how* it works, read [README.md](README.md) first. If you just want it
running, follow the steps below.

## Before you start, you need

- A working terminal. Any of these is fine:
  - **Windows, PowerShell** — supported directly; you need Python 3.10+ from
    python.org (`py --version` should work). Commands below marked *Windows*
    are the ones to use.
  - **Windows, WSL Ubuntu** — also fine, and what most of this was developed
    against. No WSL yet? See [docs/WSL_SETUP.md](docs/WSL_SETUP.md).
  - **macOS or Linux** — use the plain commands.
- An API key for `https://api.genai.mil`. Your office should have a
  process for issuing these — ask whoever sent you this repo.
- About 15 minutes the first time you set it up.

## What you'll end up with

- A local clone of this repo at a path of your choosing.
- A working Python virtualenv with the MCP server installed.
- The planner-mcp registered in your **global** OpenCode config, so it
  loads in every OpenCode session regardless of which directory you run from.
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
> it cloned into (e.g. `genai_mcp`). Your office should have shared the
> exact values.

## Step 2. Run the setup script

```sh
python3 scripts/setup.py
```

This is interactive — it asks before each significant step. It will:

1. Create a Python virtualenv at `.venv/`
2. Install the MCP server's dependencies
3. Register the planner-mcp in your **global** OpenCode config
   (`~/.config/opencode/opencode.json`) — so it loads from any directory
4. Offer to add the example provider blocks to that same global config
   (a safe merge — it never overwrites providers you already have)
5. Copy `AGENTS.example.md` to `AGENTS.md`
6. Run a healthcheck against the genai.mil endpoint

If the healthcheck step says `GENAI_MIL_API_KEY is NOT set`, do **Step 3
below** and re-run the script.

## Step 3. Set your API key (one time, persistent)

**macOS / Linux / WSL:**

```sh
echo 'export GENAI_MIL_API_KEY=your-key-here' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell)** — sets it for your user account, permanently:

```powershell
[Environment]::SetEnvironmentVariable('GENAI_MIL_API_KEY','your-key-here','User')
```

Then **open a new terminal**. The variable is read by the MCP server when it
starts, so a session that was already running keeps the old value — this is a
common source of confusing 401s after rotating a key.

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

## Step 5. Point the executor providers at your real endpoints

The setup script's Step 4 offered to add the **provider** blocks to your
global config (`~/.config/opencode/opencode.json`) — the executor models
OpenCode runs on your machine. It's a safe merge: it only adds providers
you didn't already have, and never overwrites an existing block.

**If you let setup add them**, your only remaining task is to edit the
placeholder endpoint URLs. Open `~/.config/opencode/opencode.json` and
replace the `baseURL`s for `org-gptoss` and `org-gemma` with your real
on-prem endpoints.

**If you declined** (e.g. you already maintain your own provider blocks),
merge the `provider` block from `config/providers.example.json` into the
global config by hand — keep the existing `mcp` block and any providers you
already have.

The template ships three providers:

- `org-gptoss` and `org-gemma` — your **local/on-prem executor** models.
  **Required.** Edit their `baseURL`s to your real endpoints.
- `genai-mil` — **optional.** Only needed if you want to chat with Gemini
  *directly* in OpenCode. The planner-mcp does **not** use this block — the
  MCP server reaches genai.mil on its own using `GENAI_MIL_API_KEY`. You
  can delete this provider if you only want the planner-mcp workflow.

See [config/README.md](config/README.md) for the full provider reference.

## Step 6. Try it

> **The `--model` you pass is the EXECUTOR** — the model that runs on your
> machine and does the tool calls (reading files, running code). It must be
> a **local/on-prem** model such as `org-gptoss/openai/gpt-oss-120b`. Do
> **not** pass a `genai-mil/gemini-*` model: Gemini runs remotely and cannot
> read your local files or run anything on your device. Gemini is used
> internally by the MCP — you never select it with `--model`.

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

If it works, you're done with setup. The MCP is registered globally, so it
works from any directory — `cd` to wherever your real files live and run
`opencode` there.

For **interactive** OpenCode sessions (not `opencode run`), the executor is
whatever the `model` field in your config defaults to. If that default is a
remote/cloud model, switch to a local executor with the `/models` command
once OpenCode opens — otherwise file reads and on-device execution won't
work. For a recurring workspace, drop a small `opencode.json` in that folder
with `"model": "org-gptoss/openai/gpt-oss-120b"` so it defaults correctly.

## What to do if something breaks

| Symptom | Likely fix |
|---|---|
| `GENAI_MIL_API_KEY` not set | Did Step 3, opened a new terminal. |
| Healthcheck says `401 unauthorized` | Your key is locked. Visit the URL the error provides, or contact whoever issued the key. |
| Healthcheck says `404 not found` for a model | A model name has changed. Edit `server.py`'s `_TOOL_MODEL_DEFAULTS`, or override via the `PLANNER_MODEL_*` env vars. |
| `opencode: command not found` | Step 4 didn't complete. Re-run, check for npm permission errors. |
| `opencode run` says model not found | Did Step 5 (provider blocks merged into the global config). Restart OpenCode so it picks up the new config. |
| `opencode run` errors with "Missing authorization" / 401 | Only happens if you use the optional `genai-mil` provider directly. Check that block references `{env:GENAI_MIL_API_KEY}` — exact spelling, underscores included — and that the var is set in your shell. The planner-mcp itself does not use this provider block. |
| OpenCode runs but doesn't use the MCP | Confirm Step 2 registered it: `grep planner-mcp ~/.config/opencode/opencode.json`. Restart OpenCode — the `mcp` block is read at startup. |
| Files can't be read / "passing files" fails | You're probably running with a remote model as the executor. The `--model` (or interactive default) must be a **local** model — see the callout in Step 6. |
| MCP runs but Gemini calls time out | Network — confirm you can reach `https://api.genai.mil` from this terminal: `curl -I https://api.genai.mil/v1/models`. |

If you're stuck, run the healthcheck explicitly and paste the output to
whoever's helping:

```sh
.venv/bin/python scripts/healthcheck.py            # macOS / Linux / WSL
.venv\Scripts\python scripts\healthcheck.py       # Windows
```

## What to read next

- [README.md](README.md) — what this is, how it works, the design notes
- [config/README.md](config/README.md) — config file reference, advanced setup
- [tests/README.md](tests/README.md) — how to validate changes
