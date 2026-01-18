# Main entrypoint for AgentCore runtime deployment
# This file imports and exposes the necessary components from agent.py

from agent import app, handler

# Re-export the main components
__all__ = ['app', 'handler']

if __name__ == "__main__":
    app.run()
