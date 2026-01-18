FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port for token server (Render uses 10000 by default)
EXPOSE 10000

# Set environment variable for token server port
ENV TOKEN_SERVER_PORT=10000

# Run the agent (includes embedded token server)
CMD ["python", "agent.py", "start"]
