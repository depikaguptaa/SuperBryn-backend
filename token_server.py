"""
Token server for generating LiveKit access tokens.
This allows the frontend to connect to LiveKit rooms.
"""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from livekit import api

load_dotenv()


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
        # Parse query parameters
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        if parsed.path != "/token":
            self.send_error(404, "Not Found")
            return
        
        # Get room name and participant identity
        room_name = params.get("room", ["voice-agent-room"])[0]
        identity = params.get("identity", ["user"])[0]
        
        try:
            # Create access token
            token = api.AccessToken(
                os.getenv("LIVEKIT_API_KEY"),
                os.getenv("LIVEKIT_API_SECRET"),
            )
            token.identity = identity
            token.name = identity
            
            # Grant permissions
            token.add_grant(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            ))
            
            jwt_token = token.to_jwt()
            
            # Response
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


def run_server(port: int = 8080):
    """Run the token server."""
    server = HTTPServer(("0.0.0.0", port), TokenHandler)
    print(f"Token server running on http://localhost:{port}")
    print(f"Get token: http://localhost:{port}/token?room=voice-agent-room&identity=user")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
