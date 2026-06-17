"""Shared HTTP wiring for an A2A specialist server.

Every specialist is the same Starlette app shape: an AgentExecutor behind a
DefaultRequestHandler, fronted by A2AStarletteApplication, which auto-serves the
Agent Card at /.well-known/agent-card.json and the JSON-RPC endpoint at /.
"""

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard


def build_server(card: AgentCard, executor: AgentExecutor) -> A2AStarletteApplication:
    """Wrap an executor and its card into a runnable A2A application.

    Call ``.build()`` on the result to get the ASGI app for uvicorn.
    """
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    return A2AStarletteApplication(agent_card=card, http_handler=handler)
