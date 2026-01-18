# Voice Agent Backend

AI Voice Agent backend built with LiveKit Agents, Deepgram (STT), Cartesia (TTS), and OpenRouter (LLM).

## Features

- 🎙️ Real-time voice conversation with AI
- 📅 Appointment booking with slot management (9 AM - 5 PM, 30-min slots)
- 🔧 7 tool functions for appointment CRUD operations
- 💾 Supabase database for persistent storage
- 📊 Call summary generation

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
- **OPENROUTER_API_KEY** - from [OpenRouter](https://openrouter.ai)
- **SUPABASE_URL**, **SUPABASE_ANON_KEY** - from [Supabase](https://supabase.com)

### 3. Set Up Database

Run this SQL in your Supabase SQL Editor:

```sql
-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone_number VARCHAR(20) UNIQUE NOT NULL,
  name VARCHAR(100),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments table
CREATE TABLE appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_phone VARCHAR(20) NOT NULL,
  date DATE NOT NULL,
  time TIME NOT NULL,
  description TEXT,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prevent double-booking (unique constraint on date+time for active appointments)
CREATE UNIQUE INDEX unique_active_appointment ON appointments(date, time) WHERE status = 'active';

-- Call summaries table
CREATE TABLE call_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_phone VARCHAR(20),
  summary TEXT,
  appointments_discussed JSONB,
  preferences_mentioned JSONB,
  cost_breakdown JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Run the Agent

Start the token server (for frontend authentication):
```bash
python token_server.py
```

In a separate terminal, start the agent:
```bash
python agent.py dev
```

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
User Voice → Deepgram STT → OpenRouter LLM → Cartesia TTS → User Audio
                                ↓
                          Tool Calls
                                ↓
                          Supabase DB
```

## License

MIT
