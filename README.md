# 🤖 Personal AI Agent

A fully local, private AI agent that runs on your PC. No cloud, no data leaks, completely free.

## ✨ Features

- 🎤 Voice recognition (Whisper large-v3)
- 🧠 Local AI brain (Llama 3.1 8B via Ollama)
- 🖥️ PC control (open apps, files, browser)
- 🌐 Web search and navigation
- 📸 Screenshot capture
- 🔊 Voice output
- 😴 Sleep / wake commands
- 🔒 100% local, zero data sent anywhere

## 🖥️ Requirements

- Windows 10/11
- Python 3.10+
- NVIDIA GPU (8GB+ VRAM recommended)
- 16GB RAM
- Ollama installed

## ⚙️ Installation

### 1. Clone the repo
```bash
git clone https://github.com/yourusername/my-ai-agent.git
cd my-ai-agent
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install PyTorch with CUDA (for NVIDIA GPU)
```bash
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
```

### 5. Install Ollama
Download from https://ollama.com and install.

Then pull the AI model:
```bash
ollama pull llama3.1:8b
```

### 6. Download Whisper model
The Whisper large-v3 model will auto download on first run (~3GB).

## 🚀 Running

**Step 1 — Start Ollama in one terminal:**
```bash
ollama serve
```

**Step 2 — Run the agent in another terminal:**
```bash
venv\Scripts\activate
python agent.py
```

## 🗣️ Voice Commands

| Command | Action |
|---|---|
| "Open Spotify" | Opens Spotify app |
| "Open notepad" | Opens Notepad |
| "Search for AI news" | Google search |
| "Search YouTube for lofi" | YouTube search |
| "Go to amazon.in" | Opens website |
| "Take screenshot" | Saves screenshot |
| "Volume up / down" | Controls volume |
| "Mute" | Mutes audio |
| "Lock PC" | Locks computer |
| "Sleep" | Agent goes to sleep |
| "Wake up" | Agent wakes up |
| "Goodbye" | Shuts down agent |

## 🛠️ Built With

- [Ollama](https://ollama.com) - Local LLM runner
- [Llama 3.1](https://ai.meta.com/llama/) - AI brain
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) - Voice recognition
- [PyTorch](https://pytorch.org) - GPU acceleration
- [pyttsx3](https://github.com/nateshmbhat/pyttsx3) - Text to speech
- [SoundDevice](https://python-sounddevice.readthedocs.io) - Audio recording
- [PyAutoGUI](https://pyautogui.readthedocs.io) - PC control

## ⚠️ Notes

- Ollama must be running before starting the agent
- First run downloads Whisper model (~3GB), be patient
- RTX 5060 or equivalent GPU strongly recommended
- Works best in a quiet environment

## 📝 License

MIT License - feel free to use and modify!