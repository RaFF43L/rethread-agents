import asyncio

from actions import ChatRequest, process_chat
from config.envs import envs
from config.logging import setup_logging, get_logger

setup_logging(level=envs.log_level)
logger = get_logger(__name__)


if __name__ == "__main__":
    # Uses the pieces created by scripts/seed.py.
    examples = [
        ChatRequest(
            message="adorei essa calça, ela veste 40 e combina com bota preta?",
            item_id="RT-0001",
        ),
        ChatRequest(
            message="minha cintura é 80 e quadril 104, essa calça serve?",
            item_id="RT-0001",
        ),
        ChatRequest(
            message="o que combina com essa jaqueta pra sair à noite?",
            item_id="RT-0002",
        ),
    ]

    # A single event loop: the specialist agents are cached and keep async HTTP
    # clients bound to the loop they were first used on.
    async def run_examples() -> None:
        for request in examples:
            print("\n" + "=" * 70)
            print(f"Message   : {request.message}  (item={request.item_id})")
            out = await process_chat(request)
            print(f"Intents   : {out.intents}")
            for intent, o in out.agent_outputs.items():
                print(f"  {intent}: approved={o.approved} attempts={o.attempts}")
            print(f"Response  :\n{out.response}")

    asyncio.run(run_examples())
