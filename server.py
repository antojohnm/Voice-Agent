from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
import json
import base64
import asyncio
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
from llm import chat
from database import (
    start_call, end_call, get_all_calls,
    get_call_transcript, save_recording
)
import os
import tempfile
import re 

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

current_audio_file = None
call_states = {}  # call_sid → {"is_speaking": bool, "host": str}

def format_numbers_for_speech(text):
    """Space out any number that is 4 or more digits long"""
    def space_digits(match):
        return ' '.join(list(match.group()))
    return re.sub(r'\b\d{4,}\b', space_digits, text)

def generate_elevenlabs_audio(text):
    """Generate audio using ElevenLabs and save to file. Returns None if quota exceeded."""
    from elevenlabs.client import ElevenLabs
    global current_audio_file

    text = format_numbers_for_speech(text)

    try:
        client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

        audio = client.text_to_speech.convert(
            text=text,
            voice_id="EXAVITQu4vr4xnSDxMaL",
            model_id="eleven_turbo_v2_5",
            output_format="mp3_44100_128"
        )

        if current_audio_file and os.path.exists(current_audio_file):
            os.unlink(current_audio_file)

        temp = tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
            dir=".",
            prefix="response_"
        )
        for chunk in audio:
            if chunk:
                temp.write(chunk)
        temp.close()

        current_audio_file = temp.name
        return temp.name

    except Exception as e:
        print(f"ElevenLabs failed, falling back to Twilio TTS: {e}")
        return None

def get_play_block(text, host):
    """
    Try ElevenLabs first.
    If it fails, fall back to Twilio's built-in Polly TTS.
    Returns a TwiML string — either <Play> or <Say>.
    """
    audio_path = generate_elevenlabs_audio(text)

    if audio_path:
        # ElevenLabs succeeded — use <Play>
        audio_filename = os.path.basename(audio_path)
        print(f"Using ElevenLabs audio")
        return f"<Play>https://{host}/audio/{audio_filename}</Play>"
    else:
        # ElevenLabs failed — use Twilio Polly TTS
        safe_text = text.replace("'", "").replace('"', "").replace("&", "and")
        print(f"Using Twilio Polly TTS fallback")
        return f'<Say voice="Polly.Joanna">{safe_text}</Say>'

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    safe_filename = os.path.basename(filename)
    return FileResponse(path=safe_filename, media_type="audio/mpeg")


def build_response_twiml(text, host, call_sid, verified=False):
    play_block = get_play_block(text, host)

    if verified:
        gather = f"""<Gather input="speech"
                action="https://{host}/handle-speech?call_sid={call_sid}"
                method="POST"
                speechTimeout="auto"
                timeout="15"
                language="en-IN"
                speechModel="phone_call">
            {play_block}
        </Gather>"""
    else:
        gather = f"""<Gather input="dtmf"
                action="https://{host}/handle-order-id?call_sid={call_sid}"
                method="POST"
                timeout="10"
                finishOnKey="#">
            {play_block}
        </Gather>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {gather}
</Response>"""

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Handle incoming call — greet, start recording, start listening"""
    host = request.headers.get("host")
    form_data = await request.form()

    call_sid = form_data.get("CallSid", "unknown")
    caller_number = form_data.get("From", "unknown")

    print(f"Incoming call! SID: {call_sid} From: {caller_number}")

    # Save call to database
    start_call(call_sid, caller_number)

    greeting = "Hello! Welcome to customer support. To get started, could you please type your Order ID and press hashtag to enter the ID?"
    play_block = get_play_block(greeting, host)

    try:
        from twilio.rest import Client as TwilioClient
        twilio_client = TwilioClient(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        )
        twilio_client.calls(call_sid).recordings.create(
            recording_status_callback=f"https://{host}/recording-status",
            recording_status_callback_method="POST"
        )
        print(f"[{call_sid}] Background recording started via REST API")
    except Exception as e:
        print(f"[{call_sid}] Could not start background recording: {e}")

    

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Pause length="3"/>
    <Gather input="dtmf"
            action="https://{host}/handle-order-id?call_sid={call_sid}"
            method="POST"
            timeout="15"
            finishOnKey="#">
        {play_block}
    </Gather>
</Response>"""

    return Response(content=twiml, media_type="text/xml")


@app.post("/handle-order-id")
async def handle_order_id(request: Request, call_sid: str = ""):
    host = request.headers.get("host")
    if not call_sid:
        call_sid = request.query_params.get("call_sid", "unknown")

    form_data = await request.form()
    digits = form_data.get("Digits", "").strip()

    print(f"[{call_sid}] Customer entered order ID: {digits}")

    if not digits:
        text = "I didn't receive any input. Please type your Order ID followed by the hash key."
        play_block = get_play_block(text, host)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="dtmf"
            action="https://{host}/handle-order-id?call_sid={call_sid}"
            method="POST"
            timeout="10"
            finishOnKey="#">
        {play_block}
    </Gather>
</Response>"""
        return Response(content=twiml, media_type="text/xml")

    response_text = chat(digits, call_sid=call_sid)
    print(f"[{call_sid}] Agent: {response_text}")

    from database import get_verified_order
    verified = get_verified_order(call_sid) is not None

    if verified:
        # Order verified — play response then open Deepgram stream
        play_block = get_play_block(response_text, host)
        call_states[call_sid] = {"is_speaking": False, "host": host}

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {play_block}
    <Start>
        <Stream url="wss://{host}/media-stream">
            <Parameter name="call_sid" value="{call_sid}"/>
        </Stream>
    </Start>
    <Pause length="30"/>
</Response>"""
    else:
        twiml = build_response_twiml(response_text, host, call_sid, verified=False)

    return Response(content=twiml, media_type="text/xml")

async def process_transcript(call_sid: str, transcript: str, host: str):
    """Process Deepgram transcript — get LLM response and play back."""
    from twilio.rest import Client as TwilioClient

    print(f"[{call_sid}] Deepgram STT: '{transcript}'")

    if call_sid in call_states:
        call_states[call_sid]["is_speaking"] = True

    goodbye_words = ["goodbye", "bye", "thank you", "thanks", "that's all"]
    if any(word in transcript.lower() for word in goodbye_words):
        end_call(call_sid)

    response_text = chat(transcript, call_sid=call_sid)

    if response_text is None:
        print(f"[{call_sid}] LLM failed — transferring to human agent")
        transfer_number = os.getenv("HUMAN_AGENT_NUMBER")
        if transfer_number:
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Please hold while we connect you to a human agent.</Say>
    <Dial>{transfer_number}</Dial>
</Response>"""
        else:
            twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">We are sorry, all agents are unavailable. Please call back later.</Say>
    <Hangup/>
</Response>"""
        try:
            twilio_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
            twilio_client.calls(call_sid).update(twiml=twiml)
        except Exception as e:
            print(f"[{call_sid}] Failed to update call: {e}")
        return

    print(f"[{call_sid}] Agent: {response_text}")
    play_block = get_play_block(response_text, host)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {play_block}
    <Pause length="30"/>
</Response>"""

    try:
        twilio_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        twilio_client.calls(call_sid).update(twiml=twiml)
        print(f"[{call_sid}] Response playing")
    except Exception as e:
        print(f"[{call_sid}] Failed to update call TwiML: {e}")

    estimated_duration = max(2, len(response_text.split()) * 0.4)
    await asyncio.sleep(estimated_duration)

    if call_sid in call_states:
        call_states[call_sid]["is_speaking"] = False
        print(f"[{call_sid}] Listening resumed")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """Twilio Media Stream → Deepgram live STT. Falls back to Twilio STT on error."""
    await websocket.accept()

    call_sid = "unknown"
    host = ""
    print(f"[unknown] Media stream connected — waiting for start event")

    # Read call_sid from Twilio's start event first
    async for message in websocket.iter_text():
        data = json.loads(message)
        if data.get("event") == "start":
            call_sid = data["start"].get("callSid", "unknown")
            host = call_states.get(call_sid, {}).get("host", "")
            print(f"[{call_sid}] Media stream identified")
            break

    deepgram_ws = None
    deepgram_connected = False

    try:
        

        deepgram_client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        deepgram_ws = deepgram_client.listen.asyncwebsocket.v("1")

        async def on_transcript(self, result, **kwargs):
            try:
                sentence = result.channel.alternatives[0].transcript
                if not sentence or not result.is_final:
                    return
                state = call_states.get(call_sid, {})
                if state.get("is_speaking", False):
                    print(f"[{call_sid}] Muted — ignoring: '{sentence}'")
                    return
                await process_transcript(call_sid, sentence, host)
            except Exception as e:
                print(f"[{call_sid}] Transcript error: {e}")

        async def on_error(self, error, **kwargs):
            print(f"[{call_sid}] Deepgram error: {error}")

        deepgram_ws.on(LiveTranscriptionEvents.Transcript, on_transcript)
        deepgram_ws.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model="nova-2",
            language="en-IN",
            encoding="mulaw",
            sample_rate=8000,
            endpointing=300,
            interim_results=False,
        )

        

        await deepgram_ws.start(options)
        deepgram_connected = True
        print(f"[{call_sid}] Deepgram live connection opened")

        async for message in websocket.iter_text():
            data = json.loads(message)
            if data.get("event") == "media":
                audio_chunk = base64.b64decode(data["media"]["payload"])
                await deepgram_ws.send(audio_chunk)
            elif data.get("event") == "stop":
                print(f"[{call_sid}] Stream stopped")
                break

    except WebSocketDisconnect:
        print(f"[{call_sid}] WebSocket disconnected")

    except Exception as e:
        print(f"[{call_sid}] Deepgram failed: {e} — switching to Twilio STT")
        if host and call_sid != "unknown":
            try:
                from twilio.rest import Client as TwilioClient
                twilio_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                fallback_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech"
            action="https://{host}/handle-speech?call_sid={call_sid}"
            method="POST"
            speechTimeout="auto"
            timeout="15"
            language="en-IN"
            speechModel="phone_call">
        <Say voice="Polly.Joanna">Sorry, please say your query.</Say>
    </Gather>
</Response>"""
                twilio_client.calls(call_sid).update(twiml=fallback_twiml)
                print(f"[{call_sid}] Switched to Twilio STT fallback")
            except Exception as fe:
                print(f"[{call_sid}] Fallback failed: {fe}")

    finally:
        if deepgram_connected and deepgram_ws:
            await deepgram_ws.finish()
        call_states.pop(call_sid, None)
        print(f"[{call_sid}] Stream cleaned up")

@app.post("/handle-speech")
async def handle_speech(
    request: Request,
    SpeechResult: str = Form(default=""),
    call_sid: str = ""
):
    """Handle transcribed speech from Twilio"""
    host = request.headers.get("host")

    if not call_sid:
        call_sid = request.query_params.get("call_sid", "unknown")

    print(f"[{call_sid}] Customer said: '{SpeechResult}'")

    if not SpeechResult.strip():
        sorry_text = "Sorry, I didn't catch that. Please speak or type your query followed by the hash key."
        play_block = get_play_block(sorry_text, host)

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech dtmf"
            action="https://{host}/handle-speech?call_sid={call_sid}"
            method="POST"
            speechTimeout="3"
            timeout="10"
            finishOnKey="#"
            language="en-IN"
            speechModel="phone_call">
        {play_block}
    </Gather>
</Response>"""
        return Response(content=twiml, media_type="text/xml")

    # Check if call is ending
    goodbye_words = ["goodbye", "bye", "thank you", "thanks", "that's all"]
    if any(word in SpeechResult.lower() for word in goodbye_words):
        end_call(call_sid)

    # Get LLM response
    response_text = chat(SpeechResult, call_sid=call_sid)
    print(f"[{call_sid}] Agent: {response_text}")

    twiml = build_response_twiml(response_text, host, call_sid, verified=True)
    return Response(content=twiml, media_type="text/xml")

@app.post("/handle-recording")
async def handle_recording(
    request: Request,
    call_sid: str = ""
):
    """Called by Twilio when recording is available"""
    if not call_sid:
        call_sid = request.query_params.get("call_sid", "unknown")

    form_data = await request.form()
    recording_url = form_data.get("RecordingUrl", "")
    recording_sid = form_data.get("RecordingSid", "")

    print(f"Recording available for {call_sid}: {recording_url}")

    # Save recording URL to database
    if recording_url:
        save_recording(call_sid, recording_url, recording_sid)

    return Response(content="OK", media_type="text/plain")


@app.post("/recording-status")
async def recording_status(request: Request):
    form_data = await request.form()
    status = form_data.get("RecordingStatus", "")
    recording_sid = form_data.get("RecordingSid", "")
    recording_url = form_data.get("RecordingUrl", "")
    call_sid = form_data.get("CallSid", "")

    print(f"Recording {recording_sid} status: {status}")

    if status == "completed" and recording_url and call_sid:
        save_recording(call_sid, recording_url, recording_sid)

    return Response(content="OK", media_type="text/plain")


# ── Admin routes ──

@app.get("/admin/calls")
async def view_calls():
    """View all calls in browser"""
    calls = get_all_calls()
    html = """
    <html>
    <head>
        <title>Call Centre Admin</title>
        <style>
            body { font-family: Arial; padding: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
            th { background: #4CAF50; color: white; }
            tr:nth-child(even) { background: #f2f2f2; }
            a { color: #4CAF50; }
        </style>
    </head>
    <body>
        <h1>Call Centre — All Calls</h1>
        <table>
            <tr>
                <th>Call SID (click for transcript)</th>
                <th>From</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Status</th>
                <th>Recording</th>
                <th>Messages</th>
            </tr>
    """

    for call in calls:
        recording_link = f"<a href='{call[5]}' target='_blank'>▶️ Play</a>" if call[5] else "No recording"
        html += f"""
        <tr>
            <td><a href='/admin/transcript/{call[0]}'>{call[0]}</a></td>
            <td>{call[1]}</td>
            <td>{call[2]}</td>
            <td>{call[3] or 'Active'}</td>
            <td>{call[4]}</td>
            <td>{recording_link}</td>
            <td>{call[6]}</td>
        </tr>"""

    html += "</table></body></html>"
    return Response(content=html, media_type="text/html")


@app.get("/admin/transcript/{call_sid}")
async def view_transcript(call_sid: str):
    transcript = get_call_transcript(call_sid)
    html = f"""
    <html>
    <head>
        <title>Transcript</title>
        <style>
            body {{ font-family: Arial; padding: 20px; }}
            pre {{ background: #f5f5f5; padding: 20px; border-radius: 8px; 
                   white-space: pre-wrap; word-wrap: break-word; }}
        </style>
    </head>
    <body>
        <h1>Transcript: {call_sid}</h1>
        <a href='/admin/calls'>← Back to all calls</a><br><br>
        <pre>{transcript}</pre>
    </body>
    </html>"""
    return Response(content=html, media_type="text/html")


if __name__ == "__main__":
    print("Starting AI Call Centre Server...")
    print("Server running on http://localhost:5000")
    print("Admin panel: http://localhost:5000/admin/calls")
    uvicorn.run(app, host="0.0.0.0", port=5000)
