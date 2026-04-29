import ollama
import pyttsx3
import pyautogui
import webbrowser
import glob
import urllib.parse
import os
import subprocess
import sounddevice as sd
import numpy as np
import tempfile
import wave
import torch
import time
import chromadb
from sentence_transformers import SentenceTransformer
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel
from datetime import datetime

# Check GPU
print(f"Using GPU: {torch.cuda.get_device_name(0)}")

# Load Whisper on RTX 5060
print("Loading Whisper model...")
whisper_model = WhisperModel(
    r"C:\Users\priyansh\.cache\huggingface\hub\models--Systran--faster-whisper-large-v3",
    device="cuda",
    compute_type="float16"
)
print("Whisper ready!")

# Load wake word model
print("Loading wake word model...")
wake_word_model = WakeWordModel(wakeword_models=["hey_jarvis"], inference_framework="tflite")
print("Wake word ready!")

# Load memory system
print("Loading memory system...")
memory_client = chromadb.PersistentClient(path="memory")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)
memory_collection = memory_client.get_or_create_collection("agent_memory")
print("Memory system ready!")

# Voice output setup
engine = pyttsx3.init()
engine.setProperty('rate', 175)

def speak(text):
    print(f"AI: {text}")
    engine.say(text)
    engine.runAndWait()

# Save to memory
def save_memory(user_input, ai_response):
    timestamp = datetime.now().isoformat()
    text = f"User: {user_input} | AI: {ai_response}"
    embedding = embedding_model.encode(text).tolist()
    memory_collection.add(
        documents=[text],
        embeddings=[embedding],
        ids=[timestamp]
    )

# Search memory
def search_memory(query, n=3):
    count = memory_collection.count()
    if count == 0:
        return ""
    query_embedding = embedding_model.encode(query).tolist()
    results = memory_collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n, count)
    )
    if results and results['documents']:
        return "\n".join(results['documents'][0])
    return ""

# Wait for wake word
def wait_for_wake_word():
    SAMPLERATE = 16000
    CHUNK = 1280
    print("Waiting for 'Hey Jarvis'...")
    with sd.InputStream(samplerate=SAMPLERATE, channels=1, dtype='int16', blocksize=CHUNK) as stream:
        while True:
            data, _ = stream.read(CHUNK)
            audio = np.frombuffer(bytes(data), dtype=np.int16)
            predictions = wake_word_model.predict(audio)
            for key, val in predictions.items():
                if val > 0.3:
                    print(f"Wake word detected! ({key}: {val:.2f})")
                    return

# Smart listen
def listen():
    SAMPLERATE = 16000
    CHUNK = 1024
    SILENCE_THRESHOLD = 500
    SILENCE_DURATION = 1.5
    MAX_DURATION = 10

    print("Listening...")
    frames = []
    silent_chunks = 0
    speaking = False
    max_silent_chunks = int(SILENCE_DURATION * SAMPLERATE / CHUNK)
    max_chunks = int(MAX_DURATION * SAMPLERATE / CHUNK)

    with sd.InputStream(samplerate=SAMPLERATE, channels=1, dtype='int16', blocksize=CHUNK) as stream:
        for _ in range(max_chunks):
            data, _ = stream.read(CHUNK)
            frames.append(data.copy())
            volume = np.abs(data).mean()

            if volume > SILENCE_THRESHOLD:
                speaking = True
                silent_chunks = 0
            elif speaking:
                silent_chunks += 1
                if silent_chunks > max_silent_chunks:
                    break

    if not speaking:
        return ""

    audio = np.concatenate(frames, axis=0)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLERATE)
        wf.writeframes(audio.tobytes())

    segments, _ = whisper_model.transcribe(
        tmp.name,
        beam_size=5,
        language="en",
        task="transcribe",
        condition_on_previous_text=False
    )
    text = " ".join([s.text for s in segments]).strip()
    try:
        os.remove(tmp.name)
    except:
        pass

    if text:
        print(f"You said: {text}")
    return text

# AI brain with memory
def ask_ai(prompt):
    try:
        # Search relevant memories
        memories = search_memory(prompt)
        system_prompt = """You are a helpful personal AI assistant for Priyansh. 
Keep responses short and conversational. 
Never give long explanations unless asked.
If you know something about the user from past conversations, use it naturally."""

        if memories:
            system_prompt += f"\n\nRelevant memories from past conversations:\n{memories}"

        response = ollama.chat(
            model="gemma3:12b",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        reply = response['message']['content']

        # Save to memory in background
        import threading
        threading.Thread(target=save_memory, args=(prompt, reply), daemon=True).start()

        return reply
    except Exception as e:
        speak("I had a small hiccup, please repeat that!")
        return ""

# Auto find any app on PC
def find_app(app_name):
    search_dirs = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        rf"C:\Users\priyansh\AppData\Local",
        rf"C:\Users\priyansh\AppData\Roaming",
        rf"C:\Users\priyansh\AppData\Local\Programs",
    ]
    for directory in search_dirs:
        pattern = os.path.join(directory, "**", f"*{app_name}*.exe")
        results = glob.glob(pattern, recursive=True)
        if results:
            return min(results, key=len)
    return None

# Open any app smartly
def open_app(app_name):
    try:
        subprocess.Popen(f"start {app_name}", shell=True)
        return True
    except:
        pass
    path = find_app(app_name)
    if path:
        subprocess.Popen(path)
        return True
    return False

# Web search
def web_search(query, engine="google"):
    if engine == "youtube":
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    else:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)

# PC control
def handle_command(text):
    text_lower = text.lower()

    # Go to any website
    if any(x in text_lower for x in ["go to", "navigate to", "visit"]):
        url = text_lower
        for phrase in ["go to", "navigate to", "visit"]:
            url = url.replace(phrase, "")
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        speak(f"Going to {url}!")
        return True

    # YouTube search
    if "search youtube for" in text_lower or "youtube search" in text_lower:
        query = text_lower.replace("search youtube for", "").replace("youtube search", "").strip()
        web_search(query, engine="youtube")
        speak(f"Searching YouTube for {query}!")
        return True

    # Open YouTube directly
    if "open youtube" in text_lower:
        webbrowser.open("https://www.youtube.com")
        speak("Opening YouTube!")
        return True

    # Google search
    if any(x in text_lower for x in ["search for", "search google for", "look up"]):
        query = text_lower
        for phrase in ["search google for", "search for", "look up"]:
            query = query.replace(phrase, "")
        query = query.strip()
        web_search(query, engine="google")
        speak(f"Searching Google for {query}!")
        return True

    # Open in browser ONLY if user says "in browser"
    if "open" in text_lower and "in browser" in text_lower:
        site = text_lower.replace("open", "").replace("in browser", "").strip()
        webbrowser.open(f"https://www.{site}.com")
        speak(f"Opening {site} in browser!")
        return True

    # Open any app
    if text_lower.startswith("open "):
        app_name = text_lower.replace("open ", "").strip()

        builtin = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "file explorer": "explorer.exe",
            "explorer": "explorer.exe",
            "this pc": "explorer.exe",
            "task manager": "taskmgr.exe",
            "settings": "ms-settings:",
            "paint": "mspaint.exe",
            "cmd": "cmd.exe",
            "terminal": "wt.exe",
            "word": "winword.exe",
            "excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
        }

        if app_name in builtin:
            subprocess.Popen(builtin[app_name], shell=True)
            speak(f"Opening {app_name}!")
            return True

        speak(f"Looking for {app_name} on your PC...")
        if open_app(app_name):
            speak(f"Opening {app_name}!")
        else:
            speak(f"I couldn't find {app_name} on your PC. Try saying open {app_name} in browser!")
        return True

    # Screenshot
    if "screenshot" in text_lower:
        screenshot = pyautogui.screenshot()
        screenshot.save("screenshot.png")
        speak("Screenshot taken and saved!")
        return True

    # Volume
    if "volume up" in text_lower:
        for _ in range(5):
            pyautogui.press("volumeup")
        speak("Volume increased!")
        return True

    if "volume down" in text_lower:
        for _ in range(5):
            pyautogui.press("volumedown")
        speak("Volume decreased!")
        return True

    if "mute" in text_lower:
        pyautogui.press("volumemute")
        speak("Muted!")
        return True

    # Shutdown PC
    if "shutdown pc" in text_lower or "shutdown computer" in text_lower:
        speak("Shutting down your PC in 10 seconds!")
        os.system("shutdown /s /t 10")
        return True

    # Restart PC
    if "restart pc" in text_lower or "restart computer" in text_lower:
        speak("Restarting your PC in 10 seconds!")
        os.system("shutdown /r /t 10")
        return True

    # Lock PC
    if "lock pc" in text_lower or "lock computer" in text_lower:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        speak("Locking your PC!")
        return True

    return False

# Main loop
def main():
    speak("Hello Priyansh! Say Hey Jarvis to activate me!")

    while True:
        # Wait for wake word
        wait_for_wake_word()
        speak("Yes?")

        # Keep listening for follow up commands
        last_command = ""
        while True:
            user_input = listen()

            if not user_input:
                break

            # Handle YouTube follow up
            if "youtube" in last_command and not handle_command(user_input):
                web_search(user_input, engine="youtube")
                speak(f"Searching YouTube for {user_input}!")
                last_command = ""
                continue

            last_command = user_input.lower()

            print(f"Processing: {user_input}")

            # Sleep command
            if any(word in user_input.lower() for word in ["sleep", "go to sleep", "pause"]):
                speak("Going to sleep. Say Hey Jarvis to wake me up!")
                break

            # Exit command
            if any(word in user_input.lower() for word in ["shutdown", "shut down", "exit", "goodbye", "bye"]):
                speak("Goodbye Priyansh! See you soon!")
                exit()

            # Try PC command first
            if handle_command(user_input):
                continue

            # Otherwise ask AI with memory
            response = ask_ai(user_input)
            if response:
                speak(response)

if __name__ == "__main__":
    main()