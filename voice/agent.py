"""Rethread voice agent (LiveKit Agents).

LiveKit handles the audio (VAD, STT, end of turn, interruptions, TTS); the
"brain" is the rethread-agents pipeline, called through `/chat/stream` with
`channel="voice"`. Only the text approved by the quality review is spoken.

    python agent.py start           # connects to LIVEKIT_URL, joins every new room
    python agent.py download-files  # VAD / turn detector weights (done in the image)
"""

import json
import logging
import os
from typing import Any, AsyncIterable

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    FlushSentinel,
    JobContext,
    JobProcess,
    ModelSettings,
    cli,
    llm,
    tts,
)
from livekit.plugins import elevenlabs, openai, silero
# Deprecated in favor of `livekit.agents.inference.TurnDetector`, which runs on
# LiveKit Cloud; this one runs locally, so it works with the self-hosted server.
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from rethread import RethreadClient

logger = logging.getLogger("rethread-voice")

RETHREAD_API_URL = os.getenv("RETHREAD_API_URL", "http://localhost:8000")
# gpt-live-transcribe transcribes word by word while the customer speaks; with
# gpt-4o-transcribe the realtime API only transcribes each segment after a pause.
# Live models detect pauses with a local VAD the plugin loads (no server-side VAD).
STT_MODEL = os.getenv("VOICE_STT_MODEL", "gpt-live-transcribe")
# Realtime transcription: audio streamed while the customer speaks, partial
# transcripts back live (always on for the live models).
STT_REALTIME = os.getenv("VOICE_STT_REALTIME", "true").lower() == "true"

# TTS: ElevenLabs when its key is set (natural pt-BR), OpenAI otherwise.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
TTS_PROVIDER = os.getenv("VOICE_TTS_PROVIDER") or ("elevenlabs" if ELEVENLABS_API_KEY else "openai")
ELEVENLABS_MODEL = os.getenv("VOICE_ELEVENLABS_MODEL", "eleven_flash_v2_5")
ELEVENLABS_VOICE_ID = os.getenv("VOICE_ELEVENLABS_VOICE_ID", "")
OPENAI_TTS_MODEL = os.getenv("VOICE_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("VOICE_OPENAI_TTS_VOICE", "coral")

# Data channel topic where the frontend receives the recommended pieces.
SKUS_TOPIC = "rethread.skus"

GREETING = "Oi! Sou a assistente do Rethread. Quer ajuda com tamanho ou com alguma combinação?"
TTS_INSTRUCTIONS = (
    "Fale em português do Brasil, com tom simpático e natural de atendente de brechó."
)
# Said while the pipeline works, so the customer doesn't hear seconds of silence.
# The triage writes one tied to the request ("Deixa eu ver se tenho algo da Zara.");
# this is the fallback when it doesn't.
DEFAULT_FILLER = "Só um instante, já te falo."
ERROR_REPLY = "Desculpa, tive um problema aqui. Pode repetir, por favor?"


class _PipelineLLM(llm.LLM):
    """Placeholder: AgentSession only replies to the user when it has an LLM, but
    `RethreadVoiceAgent.llm_node` replaces it, so this is never called."""

    def chat(self, **kwargs: Any) -> llm.LLMStream:
        raise NotImplementedError("replies come from the rethread-agents pipeline")


class RethreadVoiceAgent(Agent):
    def __init__(
        self,
        client: RethreadClient,
        room: rtc.Room,
        session_id: str | None,
        item_id: str | None,
    ):
        super().__init__(instructions="")  # prompts live in rethread-agents
        self._client = client
        self._room = room
        self._session_id = session_id
        self._item_id = item_id

    async def on_enter(self) -> None:
        self.session.say(GREETING)

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ) -> AsyncIterable[str | FlushSentinel]:
        """Sends the transcribed turn to the pipeline and streams its answer to TTS."""
        message = _last_user_text(chat_ctx)
        if not message:
            return

        try:
            async for event, data in self._client.stream_chat(
                message, self._session_id, self._item_id
            ):
                if event == "triage":
                    yield (data.get("ack") or DEFAULT_FILLER).strip() + " "
                    yield FlushSentinel()  # speak it now, don't wait for the answer
                elif event == "token":
                    yield data["text"]
                elif event == "done":
                    await self._publish_skus(data.get("skus") or [])
                elif event == "error":
                    logger.error(f"Pipeline error: {data.get('detail')}")
                    yield ERROR_REPLY
        except Exception:  # noqa: BLE001
            logger.exception("Failed to call the rethread-agents pipeline")
            yield ERROR_REPLY

    async def _publish_skus(self, skus: list[str]) -> None:
        """Recommended pieces go to the screen; the voice only mentions them."""
        if not skus:
            return
        try:
            await self._room.local_participant.send_text(
                json.dumps({"skus": skus}), topic=SKUS_TOPIC
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to publish SKUs")


def _last_user_text(chat_ctx: llm.ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if item.type == "message" and item.role == "user":
            return (item.text_content or "").strip()
    return ""


def _tts() -> tts.TTS:
    if TTS_PROVIDER == "elevenlabs":
        options: dict[str, Any] = {}
        if ELEVENLABS_VOICE_ID:
            options["voice_id"] = ELEVENLABS_VOICE_ID
        return elevenlabs.TTS(
            api_key=ELEVENLABS_API_KEY,
            model=ELEVENLABS_MODEL,
            language="pt",
            **options,
        )
    return openai.TTS(model=OPENAI_TTS_MODEL, voice=OPENAI_TTS_VOICE, instructions=TTS_INSTRUCTIONS)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


# Each idle process is a warm Python process with the VAD loaded; the default is one per CPU,
# which on a container that sees the host's CPUs exhausts the memory.
server = AgentServer(
    setup_fnc=prewarm,
    num_idle_processes=int(os.getenv("VOICE_IDLE_PROCESSES", "1")),
)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()

    # Set by the backend in the LiveKit token (it already checked the session
    # belongs to the user). Falls back to the room name for local testing.
    session_id = participant.attributes.get("session_id") or ctx.room.name
    item_id = participant.attributes.get("item_id") or None
    logger.info(
        f"Voice session started: room={ctx.room.name} session_id={session_id} tts={TTS_PROVIDER}"
    )

    client = RethreadClient(RETHREAD_API_URL)
    ctx.add_shutdown_callback(client.aclose)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(model=STT_MODEL, language="pt", use_realtime=STT_REALTIME),
        llm=_PipelineLLM(),
        tts=_tts(),
        turn_handling={
            "turn_detection": MultilingualModel(),
            # Each reply runs the whole pipeline and saves the turn in the session:
            # don't start it before the customer has actually finished speaking.
            "preemptive_generation": {"enabled": False},
        },
    )
    await session.start(
        agent=RethreadVoiceAgent(client, ctx.room, session_id, item_id),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(server)
