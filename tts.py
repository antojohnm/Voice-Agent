from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import os
import tempfile
import subprocess
from elevenlabs import play

load_dotenv()

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

VOICE_ID = "EXAVITQu4vr4xnSDxMaL"

def speak(text):
    print(f"Speaking: {text}")
    
    # New API method for newer ElevenLabs versions
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=VOICE_ID,
        model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128"
    )
    
    # Save to temp file
    temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    for chunk in audio:
        temp_file.write(chunk)
    temp_file.close()
    
    print(f"Audio saved: {os.path.getsize(temp_file.name)} bytes")
    
    # Play with mpv directly
    subprocess.run([
        r"C:\ProgramData\chocolatey\lib\mpvio.install\tools\mpv.exe",
        "--no-video",
        temp_file.name
    ])
    
    os.unlink(temp_file.name)


if __name__ == "__main__":
    print("TTS Test\n")
    speak("Hello! Welcome to customer support. How can I help you today?")
    speak("I'm sorry to hear that. Could you please share your order ID?")
    speak("Thank you for your patience. I'll look into that right away.")