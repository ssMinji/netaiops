# Host agent package for A2A Multi-Agent system using Strands and BedrockAgentCore
from .agent import HostAgent, root_agent, app, host_agent_task, handler
from .remote_agent_connection import RemoteAgentConnections
from .context import HostAgentContext
from .memory_hook_provider import HostMemoryHook
from .streaming_queue import HostStreamingQueue
from .utils import get_ssm_parameter
from .access_token import get_gateway_access_token

__all__ = [
    'HostAgent', 
    'root_agent', 
    'app',
    'host_agent_task',
    'handler',
    'RemoteAgentConnections',
    'HostAgentContext',
    'HostMemoryHook',
    'HostStreamingQueue',
    'get_ssm_parameter',
    'get_gateway_access_token'
]
