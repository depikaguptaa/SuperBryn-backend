# Voice Agent Backend

AI Voice Agent backend built with LiveKit Agents, Deepgram (STT), Cartesia (TTS), Groq (LLM), and Beyond Presence (Avatar).

## Features

- 🎙️ Real-time voice conversation with AI
- 👤 Beyond Presence realistic avatar integration
- 📅 Appointment booking with slot management (9 AM - 5 PM, 30-min slots)
- 🔧 7 tool functions for appointment CRUD operations
- 💾 Supabase database for persistent storage
- 📊 Call summary generation
- 🔑 Embedded token server for frontend authentication

## Setup

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required API keys:
- **LIVEKIT_URL**, **LIVEKIT_API_KEY**, **LIVEKIT_API_SECRET** - from [LiveKit Cloud](https://cloud.livekit.io)
- **DEEPGRAM_API_KEY** - from [Deepgram](https://console.deepgram.com)
- **CARTESIA_API_KEY** - from [Cartesia](https://cartesia.ai)
- **GROQ_API_KEY** - from [Groq](https://console.groq.com) (using Llama 3.3 70B)
- **SUPABASE_URL**, **SUPABASE_ANON_KEY** - from [Supabase](https://supabase.com)
- **BEYOND_PRESENCE_API_KEY** (optional) - from [Beyond Presence](https://beyondpresence.ai)

### 3. Set Up Database

Run the SQL file in your Supabase SQL Editor:

```bash
# Copy contents of supabase_schema.sql and run in Supabase SQL Editor
```

Or use the included `supabase_schema.sql` file which creates:
- `users` table - User registration by phone number
- `appointments` table - Appointment bookings with double-booking prevention
- `call_summaries` table - Conversation summaries

### 4. Run the Agent

The agent includes an embedded token server, so you only need one command:

```bash
python agent.py dev
```

This starts:
- Token server on port 8080 (configurable via `TOKEN_SERVER_PORT`)
- LiveKit agent worker

## Tool Functions

| Function | Description |
|----------|-------------|
| `identify_user` | Register/identify user by phone number |
| `fetch_slots` | Get available appointment slots for a date |
| `book_appointment` | Book an appointment (with double-booking prevention) |
| `retrieve_appointments` | Get user's appointments |
| `cancel_appointment` | Cancel an appointment |
| `modify_appointment` | Change appointment date/time |
| `end_conversation` | End call and generate summary |

## Architecture

```
User Voice → Deepgram STT → Groq LLM → Cartesia TTS → User Audio
                                ↓
                          Tool Calls
                                ↓
                          Supabase DB
                          
Beyond Presence Avatar ←── Agent Audio (lip-sync)
```

## Deployment (Render)

1. Push to GitHub
2. Connect repo to Render
3. Set environment variables from `.env.example`
4. Deploy using `render.yaml` blueprint

## License

MIT
