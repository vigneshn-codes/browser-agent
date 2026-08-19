# Browser Control Agent

A text-only browser-control agent driven by **your own** OpenAI or Anthropic
(Claude) API key. Inspired by the design of `dsh-browser` (numbered elements,
no screenshots, masked sensitive fields) but rebuilt in Python and decoupled
from DeepSeek's harness.

## How it differs from dsh-browser
- **No UI — this is a CLI, not a browser sidebar.** `dsh-browser` ships a Chrome
  extension with an in-page chat sidebar. Here you drive the agent from the
  terminal; with `HEADLESS=false` you *watch* a real Chromium window it controls,
  but there is no docked chat panel or on-page controls. See
  [Interface](#interface-cli-not-a-sidebar) below.
- **Provider-agnostic**: swap OpenAI ↔ Claude with one env var.
- **Python + Playwright** instead of a Chrome MV3 extension + Node bridge.
  Playwright drives a real Chromium (or your channel of choice) so logins,
  sessions, and cookies persist across a run.
- **Same safety model**: page text is untrusted data, passwords/cards are masked,
  high-risk actions require confirmation.

## Architecture
```
browser_agent/
  config.py            # env-driven settings + provider selection
  __main__.py          # CLI entrypoint
  llm/                 # provider-agnostic LLM clients (OpenAI, Anthropic)
  browser/             # Playwright controller -> text snapshots + actions
  tools/               # JSON tool schemas + dispatch to the browser
  guardrails/          # domain allowlist, prompt-injection screen, gates
  agent/               # the plan->act->observe loop
  playbooks.py         # auto-loads the right skill/command .md for a task
  prompts/system.md    # system prompt (role + safety rules)
  skills/*.md          # reusable capability playbooks
commands/*.md          # slash-command style task templates
tests/                 # guardrail, dispatch-loop, playbook, controller tests
```

## Setup

Requires **Python 3.10+**.

**1. Create and activate a virtual environment** (recommended):
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

**2. Install the package** (`[dev]` adds pytest):
```bash
pip install -e ".[dev]"
```

**3. Install the Chromium browser Playwright drives:**
```bash
python -m playwright install chromium
```

**4. Create your `.env` and add an API key:**
```bash
cp .env.example .env
```
Then edit `.env` and set the key for your provider (`.env` is gitignored):
```ini
LLM_PROVIDER=anthropic           # or: openai
ANTHROPIC_API_KEY=sk-ant-...     # if provider is anthropic
OPENAI_API_KEY=sk-...            # if provider is openai
```

## Key features
- **Stable element numbers.** Each snapshot is stamped with a generation token;
  controls that persist keep their number, and an index from a stale snapshot
  resolves to nothing (with a "re-snapshot" hint) instead of crashing or
  clicking the wrong element after the DOM changes.
- **`browser_wait`.** Wait for the page to settle (`networkidle`/`load`) or for a
  specific CSS selector before snapshotting or acting.
- **Delta snapshots.** `browser_snapshot(delta=true)` returns only the controls
  added/removed since the last snapshot — unchanged controls keep their numbers.
- **Persistent profile.** Set `USER_DATA_DIR` (and optionally
  `BROWSER_CHANNEL=chrome`) to reuse your logged-in sessions and cookies via
  Playwright's `launch_persistent_context`. Quit the browser first — the profile
  is locked while open; a cloned/dedicated profile dir is safest.
- **Auto skill/command loader.** A `/name args` task expands from
  `commands/name.md`; a free-form task auto-injects the best-matching
  `skills/*.md` playbook into the system prompt.

## Run

The agent takes a natural-language task and an optional domain allowlist:
```bash
python -m browser_agent "<task>" [--domains d1.com d2.com ...]
```

**Basic example** (Anthropic is the default provider):
```bash
python -m browser_agent \
  "Go to news.ycombinator.com and list the top 3 story titles" \
  --domains news.ycombinator.com
```

**Use OpenAI instead** (override the provider for one run):
```bash
LLM_PROVIDER=openai python -m browser_agent \
  "Search Wikipedia for 'Turing' and open the first result" \
  --domains wikipedia.org
```

**Run a slash command** (expands from `commands/*.md`):
```bash
python -m browser_agent "/summarize_page https://example.com" --domains example.com
```

**Watch it work vs. run headless:** set `HEADLESS=false` in `.env` (default) to
see the Chromium window; `HEADLESS=true` runs it invisibly.

Notes:
- `--domains` sandboxes navigation to those hosts (and subdomains). Omit it to
  allow any site — not recommended.
- When the agent hits a payment/delete/transfer action it pauses and asks for
  `y/N` confirmation in the terminal (while `REQUIRE_CONFIRMATION=true`).
- The console prints `[playbook] ...` when a skill/command is auto-loaded and
  `[guardrail] ...` when suspicious page text is flagged.

## Interface: CLI, not a sidebar

Unlike `dsh-browser`'s Chrome-extension sidebar, this project has **no graphical
UI**. Interaction is entirely through the terminal:

- **Input** — the task string (and flags) you pass on the command line.
- **Output** — progress logs and the final `=== RESULT ===` summary in stdout.
- **The browser window** is Chromium under Playwright's control. You can see it
  (`HEADLESS=false`) but you don't type into a chat box on the page.

This is a deliberate trade: dropping the MV3 extension + Node bridge for
Python + Playwright is what lets you bring your own API key and keep the
"page text is untrusted" screening outside the browser. If you want a UI later,
the `Agent` class in `browser_agent/agent/loop.py` is the integration point — it
already exposes `run(task) -> str`, so a thin wrapper (e.g. a FastAPI endpoint or
a Streamlit chat box) could drive it without touching the core. Ask if you'd like
one added.

## Testing
```bash
pytest -q
```
Runs guardrail, tool-dispatch (mocked LLM), playbook-loader, and real-browser
regression tests. The browser tests auto-skip if Chromium isn't installed.

## Extending
- **New tool**: add a schema to `tools/registry.py`, a controller method in
  `browser/controller.py`, and wire it in `ToolDispatcher._map`.
- **New skill**: drop a `.md` in `skills/`. Load and inject it into the system
  prompt (or a task preamble) when the trigger matches.
- **New command**: add a `.md` in `commands/` and expand it into a task string.

## Security notes
- Keys live only in `.env` (gitignored). Never commit them.
- Set `--domains` (or `allowed_domains`) to sandbox where the agent may go.
- Keep `REQUIRE_CONFIRMATION=true` for anything touching money or identity.
