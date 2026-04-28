from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
import uvicorn
import json 
import base64 
import audioop 
import wave
import io 
import os 
import tempfile 
from dotenv import load_dotenv
from llm import chat 
from tts import speak_to_bytes
from stt import transcribe

load_dotenv()

app = FastAPI()

@app.post("/incoming-call")
async def incoming_call(request:Request):
    """Handle incoming Twilio call -- return TwiML"""

    host = requst.headers.get("host")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello! Welcome to customer support. Please wait while we connect you. </Say>
</Response>"""
    
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/audio-stream")
async def audio_stream(websocket:WebSocket):
    """Handle Websocket audio stream from twilio"""

    await websocket.accept()
    print("WebSocket connection established")

    audio_buffer = bytearray()
    stream_sid = None
    silence_counter = 0
    SILENCE_LIMIT = 20

    try:
        async for message in websocket:
            data = json.loads(message)
            event = data.get("event")

            if even == "connected":
                print("Call connected")

            elif event == "start":
                stream_sid = data["start"]["streamSid"]
                print(f"Stream started: {stream_sid}")

            elif event == "media":
                payload = data["media"]["payload"]
                chunk = base64.b64decode(payload)

                rms = audioop.rms(chunk, 1)

                if rms>200:
                    audio_buffer.extend(chunk)
                    silence_counter = 0
                
                else:
                    silnce_counter += 1

                if len(audio_buffer) > 0 and silence_counter >= SILENCE_LIMIT:
                    print("Processing speech")

                    wav_bytes = mulaw_to_wav(bytes(audio_buffer))

                    user_text = transcribe_from_bytes(wav_bytes)
                    
                    if user_text and len(user_text.strip()) > 0:
                        print(f"Customer: {user_text}")

                        response_text = chat(user_text)
                        print(f"Agent: {response_text}")

                        audio_bytes = tts_to_mulaw(response_text)

                        await send_audio(websocket, stream_sid, audio_bytes)

                    audio_buffer.clear()
                    silence_counter = 0


            elif event == "stop":
                print("Call ended")
                break
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally: 
        print("Websocket closed")


def mulaw_to_wav(mulaw_bytes):
    """Convert Twilio's mulaw audio to WAV format for Whisper"""

    pcm_audio = audioop.ulaw2lin(mulaw_bytes, 2)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(pcm_audio)

    return wav_buffer.getvalue()

def transcribe_from_bytes(wav_bytes):
    """Send WAV bytes to Groq Whisper and get text"""

    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    temp.write(wav_bytes)
    temp.close()

    try:
        with open(temp.name, "rb") as f:
            result = client.audio.transcriptions.create(
                model = "whisper-large-v3",
                file = f,
                language = "en"
            )

        return result.text
    finally:
        os.unlink(temp.name)


def tts_to_mulaw(text):
    """Convert text to mulaw audio bytes for Twilio"""

    from elevenlabs.client import ElevenLabs
    import subprocess

    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

    audio = client.text_to_speech.convert(
        text=text,
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128"
    )

    mp3_temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    for chunk in audio: 
        if chunk:
            mp3_temp.write(chunk)
    mp3_temp.close()

    wav_temp = tempfle.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_temp.close()

    subprocess.run([
        "ffmpeg", "-y",
        "-i", mp3_temp.name,
        "-ar", "8000",
        "-ac","1",
        "-f", "wav",
        wav_temp.name
    ], capture_output = True)

    with wave.open(wav_temp.name, 'rb') as wav_file:
        pcm_bytes = wav_file.readframes(wav_file.getnframes())

    mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)

    os.unlink(mp3_temp.name)
    os.unlink(wav_temp.name)

    return mulaw_bytes

async def send_audio(websocket, stream_sid, mulaw_bytes):
    """Send audio back to Twilio over Websocket"""

    CHUNK_SIZE = 160
    for i in range(0, len(mulaw_bytes), CHUNK_SIZE):
        chunk = mulaw_bytes[i:i + CHUNK_SIZE]

        payload = base64.b64encode(chunk).decode("utf-8")

        message = {
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": payload
            }
        }

        await websocket.send_json(message)

    print("Audio sent to caller")


if __name__ == "__main__":
    print("Starting AI Call centre server... ")
    print("Server running on http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)