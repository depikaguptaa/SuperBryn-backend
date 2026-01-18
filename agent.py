"""
AI Voice Agent with LiveKit Agents Framework.
Integrates Deepgram (STT), Cartesia (TTS), and OpenRouter (LLM).
Includes embedded token server for single-process deployment.
"""
import os
import json
import logging
import threading
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
from livekit.plugins import deepgram, cartesia, openai
from livekit.agents.llm import ChatContext, ChatMessage

from tools import AssistantFunctions, context

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# System prompt for the assistant
SYSTEM_PROMPT = """You are a friendly and professional AI assistant for an appointment booking service. Your role is to help users:

1. Identify themselves by phone number
2. Check available appointment slots (9 AM - 5 PM, 30-minute slots)
3. Book new appointments
4. Retrieve their existing appointments
5. Cancel or modify appointments
6. Answer questions about the service

IMPORTANT GUIDELINES:
- Always ask for the user's phone number first if they want to book, view, or manage appointments
- Be conversational and natural - you're having a voice conversation
- Confirm all booking details before finalizing
- After completing a task, ask if there's anything else you can help with
- When the user says goodbye or wants to end the call, use the end_conversation function
- Keep responses concise - remember this is a voice conversation
- If the user mentions any preferences (like preferred times, communication preferences), note them

AVAILABLE HOURS: Monday to Friday, 9:00 AM to 5:00 PM
SLOT DURATION: 30 minutes each

Be warm, helpful, and efficient. Start by greeting the user and asking how you can help them today."""


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
            )
            token.identity = identity
            token.name = identity
            
            token.add_grant(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            ))
            
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
            instructions=SYSTEM_PROMPT,
            stt=deepgram.STT(
                api_key=os.getenv("DEEPGRAM_API_KEY"),
                model="nova-2",
                language="en",
            ),
            llm=openai.LLM.with_openrouter(
                model="meta-llama/llama-3.3-70b-instruct:free",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            ),
            tts=cartesia.TTS(
                api_key=os.getenv("CARTESIA_API_KEY"),
                voice="a0e99841-438c-4a64-b679-ae501e7d6091",
            ),
            fnc_ctx=AssistantFunctions(),
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
        logger.info(f"Tool call completed: {function_name}")
        
        if result == "END_CALL":
            await self.session.generate_reply(
                instructions="Thank the user for using the service and wish them a great day. Keep it brief."
            )
            import asyncio
            await asyncio.sleep(3)
            if self.session:
                await self.session.room.disconnect()
        
        tool_event = {
            "type": "tool_call_end",
            "function": function_name,
            "result": result[:500] if result else "",
            "timestamp": __import__("datetime").datetime.now().isoformat()
        }
        
        if self.session and self.session.room:
            await self.session.room.local_participant.publish_data(
                json.dumps(tool_event).encode(),
                reliable=True,
                topic="tool_calls"
            )


async def entrypoint(ctx: JobContext):
    """Main entry point for the agent."""
    logger.info(f"Starting voice agent for room: {ctx.room.name}")
    
    await ctx.connect()
    
    agent = VoiceAgent()
    session = AgentSession()
    
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            audio_enabled=True,
            video_enabled=False,
        ),
    )
    
    logger.info("Voice agent started and listening")


if __name__ == "__main__":
    # Start token server in background thread
    token_port = int(os.getenv("TOKEN_SERVER_PORT", "8080"))
    token_thread = threading.Thread(target=start_token_server, args=(token_port,), daemon=True)
    token_thread.start()
    logger.info(f"Token server started on port {token_port}")
    
    # Run the LiveKit agent
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
