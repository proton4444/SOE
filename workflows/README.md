# SOE workflows

Automation for the war-room dashboard, meant to run on the machine that holds
the game files (the server box). All scripts require the repo on the machine
and `SOE_LLM_KEY` set in the environment.

## bot_loop.py — auto-play a room

```powershell
set SOE_LLM_KEY=sk-or-v1-...
python workflows/bot_loop.py --code ABC12 --turns 20 [--force]
```

Runs every enabled bot for the given number of turns: subagents (intel +
field), strategist decision, parser-filtered orders, then a deterministic
turn resolution. See the script docstring for options.

## Model probing

`scripts/probe_model.py` (in the repo root scripts) checks that a model emits
the `--- ORDERS ---` marker and order-like lines:

```powershell
python scripts/probe_model.py openai/gpt-4o-mini qwen/qwen3-32b
```

## Deploying to the remote PC

Copy the repo (or at least `webapp/`, `workflows/`, `scripts/`, `spoils_engine/`,
`maps/`, `server_data/`, and `games/`) to the server machine, e.g.:

```powershell
robocopy C:\Antigravity\SOE \\REMOTE-PC\SOE\ /E /XD .git __pycache__ .pytest_cache .mypy_cache build spoils_engine.egg-info
```

Then on the remote PC:

```powershell
pip install -r requirements.txt
set SOE_LLM_KEY=sk-or-v1-...
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000   # dashboard
python workflows/bot_loop.py --code ABC12 --turns 20             # auto-play
```
