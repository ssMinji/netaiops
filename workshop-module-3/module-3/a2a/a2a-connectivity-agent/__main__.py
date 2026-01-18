import os
import sys
import yaml
import httpx
import uvicorn
import logging
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from utils import get_agent_config
from agent_executer import ConnectivityTroubleshootingAgentCoreExecutor

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MissingConfigError(Exception):
    pass

def required_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise MissingConfigError(f"Missing required env: {name}")
    return v

def load_config() -> dict:
    """Load configuration from config.yaml file."""
    config_path = Path(__file__).parent / "config.yaml"
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise MissingConfigError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise MissingConfigError(f"Error parsing config file: {e}")

async def health_check(request):
    """Health check endpoint for ECS health checks."""
    # Get agent ARN from config.yaml only
    agent_arn = "unknown"
    
    try:
        config = load_config()
        agent_card_info = config.get('agent_card_info', {})
        agent_arn = agent_card_info.get('agent_arn', 'unknown')
        logger.debug(f"Got agent ARN from config.yaml: {agent_arn}")
    except Exception as e:
        logger.debug(f"Could not load agent ARN from config.yaml: {e}")
        agent_arn = "unknown"
    
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "connectivity-troubleshooting-agent",
        "agent_arn": agent_arn
    })

def main():
    """Starts the AgentCore Connectivity Troubleshooting Agent A2A server."""
    print("Starting AgentCore Connectivity Troubleshooting Agent A2A server...")
    
    # Load configuration
    print("Loading configuration from config.yaml...")
    config = load_config()
    print("Configuration loaded successfully")
    
    # Server configuration with environment variable support for ECS
    host = os.getenv('HOST', config['server']['default_host'])
    port = int(os.getenv('PORT', str(config['server']['default_port'])))
    print(f"Server will start on {host}:{port}")

    try:
        # ---- Identity / Gateway config (from config.yaml and AWS Secrets Manager) ----
        print("Loading agent configuration and credentials...")
        agent_config = get_agent_config()
        print("Agent configuration loaded successfully")
        
        base_url = agent_config['base_url']
        agent_arn = agent_config['agent_arn'] 
        agent_session_id = agent_config['agent_session_id']
        user_pool_id = agent_config['user_pool_id']
        client_id = agent_config['client_id']
        client_secret = agent_config['client_secret']
        scope = agent_config['scope']
        discovery_url = agent_config.get('discovery_url')
        identity_provider = agent_config.get('identity_group')
        
        
        print(f"Base URL: {base_url}")
        print(f"Agent ARN: {agent_arn}")
        print(f"Session ID: {agent_session_id}")
        print(f"Going to use the following identity provider: {identity_provider}")
        
        # ---- A2A Agent metadata (Card + Skills) from config ----
        print("Setting up agent capabilities and skills...")
        capabilities = AgentCapabilities(
            streaming=config['agent_metadata']['capabilities']['streaming'],
            push_notifications=config['agent_metadata']['capabilities']['push_notifications']
        )

        skills = [
            AgentSkill(
                id=skill['id'],
                name=skill['name'],
                description=skill['description'],
                tags=skill['tags'],
                examples=skill['examples']
            )
            for skill in config['agent_skills']
        ]
        print(f"Loaded {len(skills)} agent skills")

        # Supported content types from config
        supported_ct = config['agent_metadata']['supported_content_types']

        # Agent card from config
        print("Creating agent card...")
        agent_card = AgentCard(
            name=config['agent_metadata']['name'],
            description=config['agent_metadata']['description'],
            url=base_url,
            version=config['agent_metadata']['version'],
            defaultInputModes=supported_ct,
            defaultOutputModes=supported_ct,
            capabilities=capabilities,
            skills=skills,
            identity_provider=identity_provider,
        )
        print(f"Agent card created successfully!")
        print(f"  Name: {agent_card.name}")
        print(f"  Description: {agent_card.description}")
        print(f"  URL: {agent_card.url}")
        print(f"  Version: {agent_card.version}")
        print(f"  Identity Provider: {identity_provider}")
        print(f"  Capabilities: streaming={agent_card.capabilities.streaming}, pushNotifications={agent_card.capabilities.push_notifications}")
        print(f"  Skills: {len(agent_card.skills)} skills loaded")
        for skill in agent_card.skills:
            print(f"    - {skill.name} ({skill.id})")

        # ---- Wire executor into the A2A app ----
        print("Initializing agent executor and request handler...")
        
        # Get timeout configuration from config
        executor_timeout = config.get('executor_config', {}).get('request_timeout_s', 900)
        print(f"Using request timeout: {executor_timeout} seconds")
        
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=ConnectivityTroubleshootingAgentCoreExecutor(
                base_url=base_url,
                agent_arn=agent_arn,
                agent_session_id=agent_session_id,
                user_pool_id=user_pool_id,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
                discovery_url=discovery_url,
                identity_provider=identity_provider,
                request_timeout_s=executor_timeout,
            ),
            task_store=InMemoryTaskStore(),
        )
        print("Agent executor initialized successfully")

        print("Creating A2A Starlette application...")
        server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
        
        # Log the agent card details for debugging
        print(f"Agent card created: {agent_card}")
        print(f"Agent card URL: {agent_card.url}")
        print(f"Agent card name: {agent_card.name}")
        
        # Check if server has app attribute or build method
        if hasattr(server, 'build'):
            app = server.build()
        elif hasattr(server, 'app'):
            app = server.app
        else:
            # Fallback: use the server object directly if it's a Starlette app
            app = server
        
        # Add health endpoint for ECS health checks
        health_route = Route("/health", health_check, methods=["GET"])
        
        # Add the health route to the app
        if hasattr(app, 'router') and hasattr(app.router, 'routes'):
            app.router.routes.append(health_route)
        elif hasattr(app, 'routes'):
            app.routes.append(health_route)
        else:
            # If we can't add routes, create a new Starlette app with the health route
            from starlette.applications import Starlette
            routes = [health_route]
            if hasattr(server, 'routes'):
                routes.extend(server.routes)
            app = Starlette(routes=routes)
        
        print("Health endpoint added to server at /health")
        print("A2A agent card will be available at /.well-known/agent-card.json")
        print(f"Starting server on http://{host}:{port}")
        
        # Start the server
        uvicorn.run(app, host=host, port=port)
        
    except Exception as e:
        logger.error("An error occurred during server startup: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
