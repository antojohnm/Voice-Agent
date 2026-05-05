# AI Call Centre

An AI-powered customer support call centre built with Twilio, Deepgram, Groq, and ElevenLabs. Handles inbound calls, identifies customers by order ID, answers order-related queries using an LLM, and stores call transcripts and recordings in a PostgreSQL database.

---

## Features

- **Inbound call handling** via Twilio
- **Order ID verification** via DTMF (keypad input)
- **Live speech-to-text** using Deepgram Nova-2 (streaming via WebSocket)
- **Twilio STT fallback** if Deepgram fails
- **LLM-powered responses** using Groq (Llama 3.1)
- **Text-to-speech** using ElevenLabs (falls back to Twilio Polly)
- **Call recording** saved to PostgreSQL
- **Full transcript storage** per call in PostgreSQL
- **Human agent transfer** if LLM fails
- **Admin panel** to view all calls, transcripts, and recordings

---

## Architecture

```
Incoming Call (Twilio)
        ↓
Customer types Order ID (DTMF)
        ↓
Order verified → Deepgram Media Stream opens
        ↓
Customer speaks → Deepgram transcribes in real time
        ↓
Transcript → Groq LLM → Response
        ↓
ElevenLabs TTS (or Twilio Polly fallback)
        ↓
Response played back to customer
        ↓
Loop continues until call ends
        ↓
Recording + transcript saved to PostgreSQL
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Phone calls | Twilio |
| Live STT | Deepgram Nova-2 |
| STT Fallback | Twilio STT |
| LLM | Groq (Llama 3.1 8B) |
| TTS | ElevenLabs |
| TTS Fallback | Twilio Polly |
| Backend | FastAPI + Uvicorn |
| Database | PostgreSQL |
| Tunnel (dev) | ngrok |

---

## Prerequisites

- Python 3.10+
- PostgreSQL
- ngrok (for local development)
- Accounts and API keys for: Twilio, Deepgram, Groq, ElevenLabs

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-call-centre.git
cd ai-call-centre
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
ELEVENLABS_API_KEY=your_elevenlabs_api_key
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
HUMAN_AGENT_NUMBER=+91xxxxxxxxxx
DB_HOST=localhost
DB_PORT=5432
DB_NAME=call_centre
DB_USER=postgres
DB_PASSWORD=your_db_password
```

### 4. Set up PostgreSQL

Create the database:

```sql
CREATE DATABASE call_centre;
```

The tables (`calls`, `messages`, `call_verifications`) are created automatically when the server starts.

Your business tables (`orders`, `customers`, `inventory`, `payments`, `deliveries`) must be populated separately.

### 5. Start ngrok

```bash
ngrok http 5000
```

Copy the HTTPS URL (e.g. `https://abc123.ngrok.io`).

### 6. Configure Twilio webhook

Go to [Twilio Console](https://console.twilio.com) → Phone Numbers → your number → Voice webhook and set it to:

```
https://abc123.ngrok.io/incoming-call
```

### 7. Run the server

```bash
python server.py
```

---

## Project Structure

```
ai-call-centre/
├── server.py         # FastAPI server — call handling, STT, TTS, WebSocket
├── llm.py            # Groq LLM integration and prompt management
├── database.py       # PostgreSQL — calls, messages, orders
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md
```

---

## Database Schema

### `calls`
| Column | Type | Description |
|--------|------|-------------|
| call_sid | TEXT | Twilio call ID (primary key) |
| caller_number | TEXT | Caller's phone number |
| started_at | TIMESTAMP | Call start time |
| ended_at | TIMESTAMP | Call end time |
| status | TEXT | active / ended |
| recording_url | TEXT | Twilio recording URL |
| recording_sid | TEXT | Twilio recording ID |

### `messages`
| Column | Type | Description |
|--------|------|-------------|
| call_sid | TEXT | Foreign key to calls |
| conversation | TEXT | Full transcript as single text block |
| last_updated | TIMESTAMP | Last message time |

### `call_verifications`
| Column | Type | Description |
|--------|------|-------------|
| call_sid | TEXT | Foreign key to calls |
| voice_code | TEXT | Verified order ID |
| verified_at | TIMESTAMP | Verification time |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/incoming-call` | Twilio webhook — handles new calls |
| POST | `/handle-order-id` | Processes DTMF order ID input |
| WS | `/media-stream` | Deepgram live audio stream |
| POST | `/handle-speech` | Twilio STT fallback |
| POST | `/recording-status` | Twilio recording callback |
| GET | `/audio/{filename}` | Serves ElevenLabs audio files |
| GET | `/admin/calls` | Admin panel — all calls |
| GET | `/admin/transcript/{call_sid}` | View call transcript |

---

## Admin Panel

Visit `http://localhost:5000/admin/calls` to view:
- All calls with timestamps and status
- Click any call SID to view its full transcript
- Play call recordings directly in the browser

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `GROQ_API_KEY` | Groq API key |
| `DEEPGRAM_API_KEY` | Deepgram API key |
| `HUMAN_AGENT_NUMBER` | Phone number to transfer calls to |
| `DB_HOST` | PostgreSQL host (default: localhost) |
| `DB_PORT` | PostgreSQL port (default: 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |

---

## Known Limitations

- ElevenLabs free tier has limited credits — falls back to Twilio Polly automatically
- ngrok URL changes on every restart — update Twilio webhook each time
- `<Pause length="30"/>` keeps the call alive for 30 seconds per turn — long silences will disconnect

---

## License

MIT
