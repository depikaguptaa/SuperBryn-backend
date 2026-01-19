"""
AI Voice Agent with LiveKit Agents Framework.
Integrates Deepgram (STT), Cartesia (TTS), and OpenRouter (LLM).
Includes embedded token server for single-process deployment.
"""
import os
import json
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

from livekit import agents, rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    RoomInputOptions,
    RunContext,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, cartesia, openai, groq, bey
from livekit.agents.llm import ChatContext, ChatMessage

from tools import TOOLS, context

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# System prompt for the assistant
SYSTEM_PROMPT = """You are a friendly and professional AI assistant for an appointment booking service. Your role is to help users:

1. Get their phone number for identification
2. Check available appointment slots (9 AM - 5 PM, 30-minute slots)
3. Book new appointments
4. Retrieve their existing appointments  
5. Cancel or modify appointments
6. Answer questions about the service

USER IDENTIFICATION FLOW:
- When a user provides their phone number, ALWAYS repeat it back to them digit by digit and ask for confirmation
- Example: "Just to confirm, your phone number is 9-5-5-9-6-3-6-1-2-2, is that correct?"
- Only proceed with identify_user function AFTER the user confirms the number is correct
- If the user says the number is wrong, ask them to provide it again
- For FIRST-TIME users: The system auto-registers them - welcome them warmly as a new user
- For RETURNING users: The system recognizes them - welcome them back and offer to help with their appointments
- Phone number is required before booking, viewing, or managing appointments

IMPORTANT GUIDELINES:
- Be conversational and natural - you're having a voice conversation
- Confirm all booking details before finalizing
- After completing a task, ask if there's anything else you can help with
- When the user says goodbye or wants to end the call, use the end_conversation function
- Keep responses concise - remember this is a voice conversation
- If the user mentions any preferences (like preferred times, communication preferences), note them

APPOINTMENT REFERENCES:
- NEVER ask users for appointment IDs - they don't know them!
- When a user says "cancel the 9 AM appointment" or "modify the 2 PM slot", YOU must match it to the correct appointment from their list
- After retrieving appointments, remember them and use the date/time to identify which one the user means
- If ambiguous (e.g., multiple appointments at same time on different days), ask for clarification using natural language like "Which date - January 20th or 21st?"
- Use the appointment ID internally when calling cancel_appointment or modify_appointment functions

CRITICAL VOICE RULES:
- NEVER read function names, parameters, dates in technical format (like 2026-01-20), or any code/JSON out loud
- NEVER read appointment IDs out loud - they are internal identifiers only
- When calling functions silently, just wait for the result and then speak naturally about what happened
- Speak dates in natural format like "January 20th" not "2026-01-20"
- Speak times naturally like "2 PM" not "14:00"
- If you need to call a function, do it silently without announcing the technical details

AVAILABLE HOURS: Monday to Friday, 9:00 AM to 5:00 PM
SLOT DURATION: 30 minutes each

Be warm, helpful, and efficient. Start by greeting the user and asking how you can help them today."""


def get_system_prompt_with_date():
    """Get system prompt with current date injected."""
    today = datetime.now()
    date_info = f"""\n\nIMPORTANT DATE INFORMATION:
- Today's date is: {today.strftime('%Y-%m-%d')} ({today.strftime('%A, %B %d, %Y')})
- When users mention dates, convert them to YYYY-MM-DD format using this as reference
- Tomorrow would be: {today.strftime('%Y')}-{today.strftime('%m')}-{str(int(today.strftime('%d')) + 1).zfill(2)}"""
    return SYSTEM_PROMPT + date_info


# ============================================================================
# EMBEDDED TOKEN SERVER
# ============================================================================

class TokenHandler(BaseHTTPRequestHandler):
    """Handle token generation requests."""
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        """Generate a token for a participant."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        # Health check endpoint
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        
        if parsed.path != "/token":
            self.send_error(404, "Not Found")
            return
        
        room_name = params.get("room", ["voice-agent-room"])[0]
        identity = params.get("identity", ["user"])[0]
        
        try:
            token = api.AccessToken(
                os.getenv("LIVEKIT_API_KEY"),
                os.getenv("LIVEKIT_API_SECRET"),
            ).with_identity(identity).with_name(identity).with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            
            jwt_token = token.to_jwt()
            
            response = {
                "token": jwt_token,
                "url": os.getenv("LIVEKIT_URL"),
                "room": room_name,
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_token_server(port: int = 8080):
    """Start the token server in a background thread."""
    server = HTTPServer(("0.0.0.0", port), TokenHandler)
    logger.info(f"Token server running on port {port}")
    server.serve_forever()


# ============================================================================
# VOICE AGENT
# ============================================================================

class VoiceAgent(Agent):
    """Custom voice agent with appointment booking capabilities."""
    
    def __init__(self):
        super().__init__(
            instructions=get_system_prompt_with_date(),
            stt=deepgram.STT(
                api_key=os.getenv("DEEPGRAM_API_KEY"),
                model="nova-2",
                language="en",
            ),
            llm=groq.LLM(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                api_key=os.getenv("GROQ_API_KEY"),
            ),
            tts=cartesia.TTS(
                api_key=os.getenv("CARTESIA_API_KEY"),
                voice="a0e99841-438c-4a64-b679-ae501e7d6091",
            ),
            tools=TOOLS,
        )
        self._pending_tool_calls = []
    
    async def on_enter(self):
        """Called when the agent enters the room."""
        await self.session.generate_reply(
            instructions="Greet the user warmly and ask how you can help them today."
        )
    
    async def on_function_call_start(self, function_name: str, arguments: dict):
        """Called when a function call starts - emit event for frontend."""
        logger.info(f"Tool call started: {function_name}")
        
        tool_event = {
            "type": "tool_call_start",
            "function": function_name,
            "arguments": arguments,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }
        
        self._pending_tool_calls.append(tool_event)
        
        if self.session and self.session.room:
            await self.session.room.local_participant.publish_data(
                json.dumps(tool_event).encode(),
                reliable=True,
                topic="tool_calls"
            )
    
    async def on_function_call_end(self, function_name: str, result: str):
        """Called when a function call completes."""
        logger.info(f"Tool call completed: {function_name}, result: {result[:100] if result else 'None'}")
        
        # Check for end conversation - by function name OR by result
        if function_name == "end_conversation" or result == "END_CALL":
            logger.info("End conversation detected! Saying goodbye and disconnecting...")
            try:
                await self.session.generate_reply(
                    instructions="Thank the user for using the service and wish them a great day. Keep it brief."
                )
                import asyncio
                await asyncio.sleep(3)
                if self.session and self.session.room:
                    logger.info("Disconnecting room...")
                    await self.session.room.disconnect()
            except Exception as e:
                logger.error(f"Error during end conversation: {e}")
        
        tool_event = {
            "type": "tool_call_end",
            "function": function_name,
            "result": result[:500] if result else "",
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }
        
        if self.session and self.session.room:
            try:
                await self.session.room.local_participant.publish_data(
                    json.dumps(tool_event).encode(),
                    reliable=True,
                    topic="tool_calls"
                )
                logger.info(f"Published tool_call_end event for {function_name}")
            except Exception as e:
                logger.error(f"Failed to publish tool event: {e}")


async def entrypoint(ctx: JobContext):
    """Main entry point for the agent."""
    logger.info(f"Starting voice agent for room: {ctx.room.name}")
    
    await ctx.connect()
    
    agent = VoiceAgent()
    session = AgentSession()
    
    # Initialize Beyond Presence Avatar (optional - only if API key is set)
    avatar_session = None
    bey_api_key = os.getenv("BEYOND_PRESENCE_API_KEY") or os.getenv("BEY_API_KEY")
    
    if bey_api_key:
        try:
            avatar_session = bey.AvatarSession(
                api_key=bey_api_key,
                # avatar_id is optional - defaults to Beyond Presence default avatar
                avatar_participant_name="AI Avatar",
            )
            logger.info("Beyond Presence avatar initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Beyond Presence avatar: {e}")
    
    # Helper to start avatar session
    async def start_avatar():
        if avatar_session:
            try:
                await avatar_session.start(
                    room=ctx.room,
                    agent_session=session,
                )
                logger.info("Beyond Presence avatar joined room")
            except Exception as e:
                logger.warning(f"Avatar session failed to start: {e}")
    
    # Start agent session and avatar session concurrently for faster loading
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            audio_enabled=True,
            video_enabled=False,
        ),
    )
    
    # Register event handler for tool calls - publish to frontend
    @session.on("function_tools_executed")
    def on_tools_executed(event):
        """Handle tool execution events and publish to frontend."""
        import asyncio
        
        # Debug: confirm handler is called
        logger.info(f"=== TOOL EVENT RECEIVED === event type: {type(event)}")
        logger.info(f"Event details: {event}")
        
        async def publish_tool_events():
            try:
                for call in event.function_calls:
                    logger.info(f"Processing tool call: {call.name}")
                    tool_event = {
                        "type": "tool_call_end",
                        "function": call.name,
                        "arguments": call.arguments if hasattr(call, 'arguments') else {},
                        "result": str(call.result)[:500] if hasattr(call, 'result') else "",
                        "timestamp": __import__("datetime").datetime.now().isoformat()
                    }
                    
                    await ctx.room.local_participant.publish_data(
                        json.dumps(tool_event).encode(),
                        reliable=True,
                        topic="tool_calls"
                    )
                    logger.info(f"Published tool event: {call.name}")
            except Exception as e:
                logger.error(f"Failed to publish tool events: {e}")
        
        asyncio.create_task(publish_tool_events())
    
    # Start avatar immediately after agent session starts (don't await fully)
    if avatar_session:
        import asyncio
        asyncio.create_task(start_avatar())
    
    logger.info("Voice agent started and listening")


if __name__ == "__main__":
    # Start token server in background thread
    token_port = int(os.getenv("TOKEN_SERVER_PORT", "8080"))
    token_thread = threading.Thread(target=start_token_server, args=(token_port,), daemon=True)
    token_thread.start()
    logger.info(f"Token server started on port {token_port}")
    
    # Run the LiveKit agent
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
