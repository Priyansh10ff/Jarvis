# Jarvis

A personal AI assistant that lives on your PC. It wakes when you call it, talks back, and controls your computer by voice or text, without ever leaking your private data.

> Status: v2 rebuild in progress. Built one feature at a time.

## Progress

- [x] Phase 0: clean slate, config, API keys in a gitignored .env
- [ ] Phase 1: core + voice (autostart, greeting, wake word, sleep)
- [ ] Phase 2: brain (Groq / Claude / local routing, tool calling)
- [ ] Phase 3: security v1
- [ ] Phase 4: overlay, typing bar, tray
- [ ] Phase 5: control layers (direct, app structure, vision, verify)

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
