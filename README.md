# Jarvis

A personal AI assistant that lives on your PC. It wakes when you call it, talks back, and controls your computer by voice or text, without ever leaking your private data.

> Status: v2 rebuild in progress. Built one feature at a time.

## Progress

- [x] Phase 0: clean slate, config, API keys in a gitignored .env
- [x] Phase 1: core + voice (autostart, greeting, always-listening or "hey" wake, sleep)
- [x] Phase 2: brain (Groq / Claude / local routing, tool calling)
- [x] Phase 3: security v1 (policy layer, confirmations, redaction, audit log)
- [x] Phase 4: orb overlay, notch typing bar, tray
- [x] Phase 5: control everything (app control, WhatsApp messaging, browser, screen vision)
- [ ] Phase 6: dev mode (projects, Claude Code, git)
- [ ] Phase 7: memory + proactive
- [ ] Phase 8: security v2
- [ ] Phase 9: house, phone, MCP
- [ ] Phase 10: launch

## Setup (Windows)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

API keys go in `.env` (gitignored). Copy the template and fill in the keys you have; one is enough:

```powershell
copy .env.example .env
python -m core.secrets
```

Run:

```powershell
python -m core.main
```

## Config

- `config/settings.yaml`: shared defaults (assistant name, user name, logging)
- `config/settings.local.yaml`: your machine-only overrides, gitignored

## License

MIT
