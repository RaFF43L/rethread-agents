from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from actions import ChatRequest, ChatResponse, process_chat, process_chat_stream
from actions import catalog as catalog_actions
from actions.catalog import NotFoundError
from catalog.schemas import (
    ItemCreate,
    ItemOut,
    ItemSearchHit,
    ItemSearchRequest,
    ItemStatus,
    ItemUpdate,
    SizeEquivalenceIn,
    SizeEquivalenceOut,
)
from config.envs import envs
from config.logging import setup_logging, get_logger

setup_logging(level=envs.log_level)
logger = get_logger(__name__)


def _run_migrations() -> None:
    """Applies pending Alembic migrations before starting the application."""
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(project_root, "alembic.ini")
    if not os.path.exists(ini_path):
        return

    from alembic.config import Config
    from alembic import command

    try:
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option(
            "script_location", os.path.join(project_root, "migrations")
        )
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations applied (alembic upgrade head).")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to apply migrations: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {envs.app_name} (env={envs.app_env})")
    logger.info(
        f"Models: large={envs.llm_provider}:{envs.model} "
        f"fast={envs.fast_provider or envs.llm_provider}:{envs.model_fast} "
        f"embed={envs.embed_provider}:{envs.embed_model}"
    )
    _run_migrations()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="rethread-agents",
    description="Atendimento do brechó: roteador + stylist + tamanho/caimento (LangGraph)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Simple healthcheck."""
    return {"status": "ok", "app": envs.app_name, "env": envs.app_env}


# --------------------------------------------------------------------------- #
# Chat — router + specialists
# --------------------------------------------------------------------------- #
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """HTTP transport: delegates to the `process_chat` action (blocking)."""
    try:
        return await process_chat(request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error executing chat")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """SSE transport: events `triage`, `specialist`, `tool`, `quality`, `status`,
    `token`, `done`, `error`."""
    return StreamingResponse(
        process_chat_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------- #
# Catalog — pieces (fill in the measurements as you go)
# --------------------------------------------------------------------------- #
@app.post("/items", response_model=ItemOut, status_code=201)
async def create_item(data: ItemCreate) -> ItemOut:
    """Registers a piece. Measurements can be partial and completed later via PATCH."""
    return await run_in_threadpool(catalog_actions.create_item, data)


@app.get("/items", response_model=list[ItemOut])
async def list_items(
    status: ItemStatus | None = None, category: str | None = None, limit: int = 100
) -> list[ItemOut]:
    return await run_in_threadpool(catalog_actions.list_items, status, category, limit)


@app.post("/items/search", response_model=list[ItemSearchHit])
async def search_items(request: ItemSearchRequest) -> list[ItemSearchHit]:
    """Same semantic search the stylist uses (active pieces only)."""
    return await run_in_threadpool(catalog_actions.search_items, request)


@app.post("/items/reindex")
async def reindex_items(only_missing: bool = True) -> dict:
    """(Re)generates embeddings — e.g. after the embedding provider was offline."""
    count = await run_in_threadpool(catalog_actions.reindex_items, only_missing)
    return {"embedded": count}


@app.get("/items/{ref}", response_model=ItemOut)
async def get_item(ref: str) -> ItemOut:
    """Fetches a piece by id or SKU."""
    try:
        return await run_in_threadpool(catalog_actions.get_item, ref)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/items/{ref}", response_model=ItemOut)
async def update_item(ref: str, data: ItemUpdate) -> ItemOut:
    """Partial update. `measurements` is merged; send a measurement as null to remove it."""
    try:
        return await run_in_threadpool(catalog_actions.update_item, ref, data)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Size equivalence table (label size -> body measurements, per brand/era)
# --------------------------------------------------------------------------- #
@app.post("/size-equivalences", response_model=SizeEquivalenceOut, status_code=201)
async def create_size_equivalence(data: SizeEquivalenceIn) -> SizeEquivalenceOut:
    return await run_in_threadpool(catalog_actions.create_size_equivalence, data)


@app.get("/size-equivalences", response_model=list[SizeEquivalenceOut])
async def list_size_equivalences(category: str | None = None) -> list[SizeEquivalenceOut]:
    return await run_in_threadpool(catalog_actions.list_size_equivalences, category)
