import sounddevice as sd
import numpy as np
import wave
import os
import json

# Sentences for Priyansh to read
SENTENCES = [
    "Open Google Chrome",
    "Search for the latest news",
    "What is the weather today",
    "Open Spotify and play music",
    "Take a screenshot",
    "Volume up please",
    "Open file explorer",
    "Search YouTube for lofi music",
    "What time is it right now",
    "Open Notepad and write something",
    "Go to Amazon dot in",
    "Lock my PC",
    "Open calculator",
    "Search for Python tutorials",
    "What is artificial intelligence",
    "Open task manager",
    "Volume down please",
    "Go to GitHub dot com",
    "Search YouTube for coding tutorials",
    "Open settings",
    "What is machine learning",
    "Take a screenshot now",
    "Search for football scores",
    "Open paint",
    "What is the capital of India",
    "Search Google for best laptops",
    "Open terminal",
    "Go to Instagram dot com",
    "What is quantum computing",
    "Search for latest cricket scores",
    "Open word",
    "What is deep learning",
    "Search YouTube for gaming videos",
    "Go to YouTube dot com",
    "Open excel",
    "What is my name",
    "Search for best movies 2025",
    "Open command prompt",
    "What is the meaning of life",
    "Search YouTube for music videos",
    "Go to Google dot com",
    "Open powerpoint",
    "What is natural language processing",
    "Search for top programming languages",
    "Open file explorer",
    "What is a neural network",
    "Search YouTube for tech reviews",
    "Go to Twitter dot com",
    "What is blockchain",
    "Search for best restaurants near me",
]

SAMPLERATE = 16000
DURATION = 5
OUTPUT_DIR = "voice_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def record_sentence(sentence, index):
    print(f"\n[{index+1}/{len(SENTENCES)}] Please say:")
    print(f">>> {sentence} <<<")
    input("Press ENTER when ready to record...")
    
    print("Recording in 3...")
    sd.sleep(1000)
    print("2...")
    sd.sleep(1000)
    print("1...")
    sd.sleep(1000)
    print("🎙️ RECORDING NOW - Speak!")
    
    audio = sd.rec(int(DURATION * SAMPLERATE), samplerate=SAMPLERATE, channels=1, dtype='int16')
    sd.wait()
    
    print("✅ Done!")
    
    # Save wav
    filename = os.path.join(OUTPUT_DIR, f"recording_{index:03d}.wav")
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLERATE)
        wf.writeframes(audio.tobytes())
    
    return filename

def main():
    print("=" * 50)
    print("🎙️ Voice Recording Session for Whisper Fine-tuning")
    print("=" * 50)
    print(f"We'll record {len(SENTENCES)} sentences.")
    print("Speak clearly and naturally in your normal voice.")
    print("You can take breaks between recordings.")
    print("=" * 50)
    
    recordings = []
    
    for i, sentence in enumerate(SENTENCES):
        filename = record_sentence(sentence, i)
        recordings.append({
            "audio": filename,
            "text": sentence
        })
        
        # Save progress after each recording
        with open("voice_data/recordings.json", "w") as f:
            json.dump(recordings, f, indent=2)
        
        print(f"Progress saved! ({i+1}/{len(SENTENCES)} done)")
        
        # Optional break every 10 recordings
        if (i + 1) % 10 == 0 and i + 1 < len(SENTENCES):
            print("\n🎉 Good job! Take a short break if needed.")
            input("Press ENTER to continue...")
    
    print("\n" + "=" * 50)
    print("✅ All recordings done!")
    print(f"Saved to: {OUTPUT_DIR}/")
    print("Now run: python finetune_whisper.py")
    print("=" * 50)

if __name__ == "__main__":
    main()