"""
This is a class that manages remote connections to agents. This 
class takes an agent card and an agent URL, and then sets up an HTTP
client, along with the A2A client set up with the agent card, the agent
URL. This file then returns the agent and also implements a send message function
to send messages to the remote agent and returns responses.
"""

from typing import Callable
import logging

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from dotenv import load_dotenv

load_dotenv()

# Enhanced logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        """
        This init function contains information about the agents that need to be connected from remote
        servers to the clients and this contains functions to get the agent card, the conversation details
        and sending the message to the remote agent
        """
        logger.info(f"🔧 Initializing RemoteAgentConnection for {agent_card.name}")
        logger.debug(f"Agent card: {agent_card}")
        logger.debug(f"Agent URL: {agent_url}")
        
        print(f"agent_card: {agent_card}")
        print(f"agent_url: {agent_url}")
        
        # Create HTTP client with proper headers for authentication
        headers = {
            "User-Agent": "A2A-Collaborator-Agent/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"HTTP client headers: {headers}")
        
        # Enhanced timeout configuration for A2A communication
        timeout_config = httpx.Timeout(
            connect=120.0,  # 2 minutes to establish connection
            read=300.0,     # 5 minutes to read response (for complex analysis like traffic mirroring)
            write=120.0,    # 2 minutes to write request
            pool=600.0      # 10 minutes for pool operations
        )
        
        self._httpx_client = httpx.AsyncClient(
            timeout=timeout_config,
            headers=headers,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        logger.info(f"✅ HTTP client configured for {agent_card.name}")
        
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card
        self.conversation_name = None
        self.conversation = None
        self.pending_tasks = set()
        
        logger.info(f"🎯 RemoteAgentConnection initialized successfully for {agent_card.name}")

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self, message_request: SendMessageRequest
    ) -> SendMessageResponse:
        """Send a message to the remote agent with enhanced logging and error handling."""
        logger.info(f"📤 Sending message to {self.card.name}")
        logger.debug(f"Message request ID: {message_request.id}")
        logger.debug(f"Message content: {message_request.params}")
        
        try:
            logger.debug(f"Calling A2A client send_message for {self.card.name}")
            response = await self.agent_client.send_message(message_request)
            logger.info(f"✅ Successfully received response from {self.card.name}")
            logger.debug(f"Response: {response}")
            return response
            
        except httpx.ConnectError as e:
            logger.error(f"❌ Connection error sending message to {self.card.name}: {e}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"⏰ Timeout error sending message to {self.card.name}: {e}")
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP status error sending message to {self.card.name}: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error sending message to {self.card.name}: {e}", exc_info=True)
            raise
