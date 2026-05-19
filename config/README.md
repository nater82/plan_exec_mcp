# Config templates

Drop-in OpenCode configuration to get a teammate from zero to a working
planner-executor setup. None of these files are loaded automatically — copy
and adapt.

## Files

| File | What it is |
|---|---|
| `providers.example.json` | Provider definitions: the genai.mil endpoint (Gemini Pro + Flash for the planner side) and two example local/on-prem executor providers (`org-gptoss` and `org-gemma`) with placeholder URLs. **Replace the placeholder URLs with whatever your organization actually hosts** — Ollama, vLLM, llama.cpp, an internal LLM gateway, anything OpenAI-compatible. Merge into your `~/.config/opencode/opencode.json` under `provider`. |
| `opencode.example.json` | MCP registration template. Wires this repo's `server.py` into OpenCode. Replace `__GENAI_MCP_DIR__` with the absolute path to your clone. |
| `AGENTS.example.md` | Executor system-prompt addendum. Pushes the executor toward "default-deny on freelancing" so it actually uses the planner-mcp tools instead of producing its own analysis/drafts. Merge into your `AGENTS.md` or equivalent. |

## Quickstart (assuming you already use OpenCode)

```sh
# 1. Clone, install, set your API key
git clone git@github.com:nater82/plan_exec_mcp.git ~/plan_exec_mcp
cd ~/plan_exec_mcp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export GENAI_MIL_API_KEY=your-key-here

# 2. Verify the genai.mil endpoint works for you
.venv/bin/python scripts/healthcheck.py

# 3. Wire the MCP into your OpenCode config
#    (replace __GENAI_MCP_DIR__ in the template, then merge)
sed "s|__GENAI_MCP_DIR__|$HOME/plan_exec_mcp|g" config/opencode.example.json > /tmp/mcp_snippet.json
#    Then manually merge /tmp/mcp_snippet.json into your ~/.config/opencode/opencode.json
#    (or use it as a local opencode.json in a working directory).

# 4. (Optional) Add the executor instructions
cat config/AGENTS.example.md >> ~/.config/opencode/AGENTS.md

# 5. Run — incident processing:
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at /path/to/report.txt and produce a safety officer notification."

# Or any research/synthesis/drafting task:
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Summarize the key SOPs referenced in /path/to/manual.pdf for new arrivals."
```

## Bring your own provider

`providers.example.json` ships with placeholder URLs (`https://your-internal-llm-endpoint/v1`). You need to replace these with real endpoints before anything will run. The MCP works with any OpenAI-compatible API:

- **Ollama** (local): `http://localhost:11434/v1` with whatever model you've pulled
- **vLLM** (local or remote): wherever your vLLM instance is serving
- **llama.cpp / LM Studio** (local): `http://localhost:1234/v1` (LM Studio default)
- **Internal LLM gateway** (your org's hosted endpoint): the URL your org provides
- **OpenRouter, Together, Groq, etc.** (cloud): per provider docs

The provider name (`org-gptoss`, `org-gemma`) is just a label — pick whatever's meaningful for your setup. The model IDs (`openai/gpt-oss-120b`, `google/gemma-4-31B-it`) are the actual model identifiers the endpoint expects.

This MCP was designed and tested with GPT-OSS 120B and Gemma 4 31B as the executor models because those are what was available, but any model with reasonable tool-calling support should work. Stronger executors will short-circuit the MCP more aggressively (which can be desirable); weaker ones will lean on it more.

## Quickstart (going from nothing → running OpenCode)

```sh
# Install OpenCode
npm install -g opencode
# or follow https://opencode.ai/docs/install

# Set up your global config from the providers template
mkdir -p ~/.config/opencode
cp config/providers.example.json ~/.config/opencode/opencode.json

# Set your API key
export GENAI_MIL_API_KEY=your-key-here
# Add this to your shell rc file so it persists.

# Now follow steps 1-5 from the previous section.
```

## Notes

- **No inline comments in the JSON.** OpenCode strictly validates its config
  schema and rejects unknown keys (including `_comment` fields). All
  documentation lives in this README. If you fork these templates, keep
  comments out of the JSON or OpenCode will refuse to load it.
- **Env var expansion.** OpenCode expands `{env:VAR_NAME}` references at
  config-load time. That's how the genai-mil provider picks up your API key
  from `$GENAI_MIL_API_KEY`. Do not hardcode the key in the config file.
- **MCP env vars are inherited.** When OpenCode spawns the MCP subprocess,
  it inherits the parent shell's environment. So `GENAI_MIL_API_KEY` only
  needs to be set in the shell where you run `opencode`.
- **Provider blocks vs MCP blocks.** Provider blocks live under `provider`;
  MCP blocks live under `mcp`. They are independent — adding the MCP does
  not require any provider changes, and the providers are useful even
  without the MCP.
- **A/B testing tool descriptions.** `opencode.example.json` registers
  both heavy and light MCP variants (light disabled by default). Toggle
  `enabled` to compare.
