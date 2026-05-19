# WSL setup for Windows users

If you're on a Windows machine and don't yet have a Linux environment, this
guide gets you to a working prompt where you can clone this repo and run
the setup script. Target audience: technical but not necessarily a daily
command-line user.

If you're on macOS or Linux, skip this — you already have a terminal that
works. Go to the main [README](../README.md).

## What you're installing

- **WSL2** — Windows Subsystem for Linux. Lets you run a real Linux
  environment inside Windows. Faster and more compatible than Git Bash for
  Python tooling.
- **Ubuntu** — the Linux distribution we'll run on top of WSL. (Other distros
  work too, but Ubuntu is the easiest path.)
- **Python, git, Node.js** — needed by this repo and by OpenCode.
- **OpenCode** — the CLI agent harness that hosts the MCP server.

## Step 1. Install WSL2 + Ubuntu

1. Press the Windows key, type **PowerShell**, right-click, choose **Run as
   administrator**.
2. In the PowerShell window, run:
   ```powershell
   wsl --install
   ```
   This downloads Ubuntu and configures WSL2. It usually takes 5-15 minutes.
3. When prompted, **reboot your machine**.
4. After reboot, Ubuntu opens automatically. The first launch sets up your
   user account — you'll be asked for:
   - **Username** — short, lowercase, no spaces (this is your Linux user, separate from your Windows login). Suggested: your first initial + last name.
   - **Password** — used for `sudo` commands. **Type carefully — it doesn't show characters as you type.** You won't be asked for it often, but you do need to remember it.

You're now at an Ubuntu prompt that looks like:
```
youruser@yourmachine:~$
```

**Verify WSL2 is working:** in the Ubuntu terminal, run `wsl.exe -l -v` and
confirm the version says `2`. If it says `1`, run `wsl --set-default-version
2` in PowerShell-as-admin and reinstall the Ubuntu distro.

## Step 2. Install Python, git, and curl

In the Ubuntu terminal:

```sh
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git curl
```

You'll be asked for the password you set in Step 1. Type it and press Enter
(no characters will show).

Verify:

```sh
python3 --version   # should print Python 3.10 or later
git --version
```

## Step 3. Install Node.js (for OpenCode)

```sh
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
source ~/.bashrc
nvm install --lts
node --version
```

## Step 4. Install OpenCode

```sh
npm install -g opencode-ai
opencode --version
```

(If you hit permission errors, you may need `sudo` or to configure npm's
global directory. See https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally.)

## Step 5. Clone this repo

```sh
cd ~
git clone <REPO_URL>          # placeholder — get the URL from the repo maintainer
cd <REPO_NAME>                # placeholder — `cd` into the folder it cloned to
```

> **Placeholders:** Replace `<REPO_URL>` and `<REPO_NAME>` with the values
> for this repo. Your office should have shared these.

## Step 6. Set your API key

You need a key for `https://api.genai.mil`. Your office should have a
process for issuing these.

Once you have a key, add it to your shell environment so every terminal
session picks it up:

```sh
echo 'export GENAI_MIL_API_KEY=your-key-here' >> ~/.bashrc
source ~/.bashrc
```

(Replace `your-key-here` with your actual key. Do NOT put the key in any
file inside this repo — `~/.bashrc` is the right place.)

## Step 7. Run this repo's setup script

```sh
python3 scripts/setup.py
```

The script will:

- Create a Python virtual environment in `.venv/`
- Install the MCP server's dependencies
- Generate a working `opencode.json` and `AGENTS.md` from the templates in
  `config/` (with the absolute path to your clone of the repo)
- Run a healthcheck against the genai.mil endpoint to verify your key works

Follow the script's output — it tells you the next command to run.

## Step 8. Try it

```sh
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Process the incident report at tests/test_report.txt and produce a safety-officer notification."
```

Or for any task that needs research / synthesis / drafting:

```sh
opencode run --model org-gptoss/openai/gpt-oss-120b \
  "Read AGENTS.md and server.py and produce a one-page architectural overview for a new contributor."
```

You should see Gemini-driven planning happen via the MCP, and the executor
produce a structured output. Takes 2-3 minutes end-to-end.

## Troubleshooting

### `wsl --install` fails or hangs
- Make sure virtualization is enabled in BIOS/UEFI. (Search your machine's
  model + "enable virtualization" if unsure.)
- On corporate machines, IT may have policies that block WSL — talk to your
  helpdesk.

### `python3 --version` returns Python 3.8 or older
- Run `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update && sudo apt install -y python3.12 python3.12-venv`, then use `python3.12` instead of `python3` in subsequent commands.

### `opencode run` says "model not found"
- The `org-gptoss` and `genai-mil` providers need to be configured in your
  OpenCode config. See `config/README.md` in this repo — copy
  `config/providers.example.json` to `~/.config/opencode/opencode.json`
  (or merge into your existing one).

### `opencode run` errors with `unauthorized` or `401`
- Your `GENAI_MIL_API_KEY` is missing, wrong, or your key has been locked.
  Visit the unlock URL the error provides, or contact whoever issued the key.

### Files in WSL don't appear in Windows Explorer
- WSL files live at `\\wsl$\Ubuntu\home\<youruser>\` in Windows Explorer.
  You can drag-and-drop normally, but prefer working entirely inside WSL
  for performance reasons — files that live on the Windows side are 10×
  slower to access from Linux tools.

### Need to use VS Code from WSL
- Install the "Remote - WSL" extension in VS Code on the Windows side. Then
  from your Ubuntu terminal: `code .` will open VS Code attached to WSL.
