"""Gemini AI adapter: chat (streaming + tool calling), embeddings, STT and TTS.
STT/TTS are gracefully disabled with a clear message since Gemini has no native
equivalents. All provider errors are translated into AIUnavailable with a
user-safe message — the raw API error never reaches the client.
"""
import logging
from typing import AsyncIterator, Awaitable, Callable

import numpy as np
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError

from ..config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)

_client: genai.Client | None = None


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class AIUnavailable(Exception):
    """Raised when a model/service cannot be used. str(e) is safe to show users."""


# ---------------------------------------------------------------------------
# Client / configuration helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True only when a Gemini API key is present."""
    return bool(settings.gemini_api_key)


def get_client() -> genai.Client:
    global _client
    if not is_configured():
        raise AIUnavailable(
            "AI features are not configured on the server. "
            "Set GEMINI_API_KEY in the .env file and restart the backend."
        )
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def translate_error(e: Exception) -> AIUnavailable:
    log.warning("Gemini API error: %s – %s", type(e).__name__, e)
    if isinstance(e, ClientError):
        code = getattr(e, "status_code", None) or getattr(e, "code", None)
        if code in (401, 403):
            return AIUnavailable(
                "The Gemini API rejected the key or this model is not allowed. "
                "Check GEMINI_API_KEY and GEMINI_CHAT_MODEL in .env."
            )
        if code == 429:
            return AIUnavailable(
                "Gemini rate limit or quota reached. Please try again in a moment."
            )
        if code == 404:
            return AIUnavailable(
                "The configured Gemini model was not found. "
                "Check GEMINI_CHAT_MODEL in .env."
            )
        if code == 400:
            return AIUnavailable(
                "Gemini could not process this request "
                "(it may be too long or contain unsupported content)."
            )
    if isinstance(e, APIError):
        msg = str(e).lower()
        if "timeout" in msg or "deadline" in msg:
            return AIUnavailable(
                "Gemini took too long to respond. Please try again."
            )
        if "connect" in msg or "network" in msg:
            return AIUnavailable(
                "Could not reach the Gemini API. "
                "Check the server's internet connection."
            )
    return AIUnavailable("Gemini returned an error. Please try again.")


# ---------------------------------------------------------------------------
# Message-format helpers (OpenAI-style → Gemini Contents)
# ---------------------------------------------------------------------------

def _build_contents(
    messages: list[dict],
) -> tuple[str | None, list[types.Content]]:
    """Convert OpenAI-style message list into (system_instruction, contents).

    Roles:
      system    → concatenated into system_instruction string (not in contents)
      user      → Content(role="user", parts=[...])
      assistant → Content(role="model", parts=[...])
      tool      → Content(role="user", parts=[FunctionResponse])

    Content may be a plain str or a multipart list[dict] with text / image_url items.
    Consecutive same-role turns are merged so Gemini's strict alternation is met.
    """
    system_parts: list[str] = []
    contents: list[types.Content] = []

    def _append(role: str, parts: list) -> None:
        """Append a Content, merging consecutive same-role entries."""
        if contents and contents[-1].role == role:
            contents[-1].parts.extend(parts)
        else:
            contents.append(types.Content(role=role, parts=parts))

    for msg in messages:
        role = msg["role"]
        content = msg.get("content")

        # ── system ──────────────────────────────────────────────────────────
        if role == "system":
            if isinstance(content, str) and content:
                system_parts.append(content)
            continue

        # ── tool result ──────────────────────────────────────────────────────
        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            # Resolve the function name from the preceding model turn
            fn_name = tool_call_id
            for prev in reversed(contents):
                if prev.role == "model":
                    for part in prev.parts or []:
                        fc = getattr(part, "function_call", None)
                        if fc and (fc.id == tool_call_id or fc.name == tool_call_id):
                            fn_name = fc.name
                            break
            _append("user", [
                types.Part.from_function_response(
                    name=fn_name,
                    response={"output": content or ""},
                )
            ])
            continue

        # ── assistant with tool_calls ────────────────────────────────────────
        if role == "assistant" and msg.get("tool_calls"):
            import json as _json
            parts: list = []
            if content:
                parts.append(types.Part.from_text(text=content))
            for tc in msg["tool_calls"]:
                try:
                    args = _json.loads(tc["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                parts.append(types.Part.from_function_call(
                    name=tc["function"]["name"],
                    args=args,
                ))
            _append("model", parts)
            continue

        gemini_role = "model" if role == "assistant" else "user"

        # ── plain string ─────────────────────────────────────────────────────
        if isinstance(content, str):
            _append(gemini_role, [types.Part.from_text(text=content)])
            continue

        # ── multipart list ───────────────────────────────────────────────────
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append(types.Part.from_text(text=item["text"]))
                elif item.get("type") == "image_url":
                    url: str = item["image_url"]["url"]
                    if url.startswith("data:"):
                        header, b64 = url.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                        import base64 as _b64
                        parts.append(types.Part.from_bytes(
                            data=_b64.b64decode(b64),
                            mime_type=mime,
                        ))
                    else:
                        parts.append(
                            types.Part.from_uri(file_uri=url, mime_type="image/jpeg")
                        )
            if parts:
                _append(gemini_role, parts)

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents


def _build_tools(openai_tools: list[dict]) -> list[types.Tool]:
    """Convert OpenAI function-tool definitions into Gemini Tool objects."""
    from google.genai.types import FunctionDeclaration, Schema, Tool

    declarations = []
    for t in openai_tools:
        fn = t.get("function", {})
        params_raw = fn.get("parameters", {})
        props = {}
        for pname, pdef in params_raw.get("properties", {}).items():
            ptype = pdef.get("type", "string").upper()
            props[pname] = Schema(type=ptype, description=pdef.get("description", ""))
        param_schema = Schema(
            type="OBJECT",
            properties=props,
            required=params_raw.get("required", []),
        )
        declarations.append(FunctionDeclaration(
            name=fn["name"],
            description=fn.get("description", ""),
            parameters=param_schema,
        ))
    return [Tool(function_declarations=declarations)] if declarations else []


# ---------------------------------------------------------------------------
# Public AI functions
# ---------------------------------------------------------------------------

ToolRunner = Callable[[str, str], Awaitable[str]]


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_runner: ToolRunner | None = None,
    max_rounds: int = 3,
) -> AsyncIterator[dict]:
    """Yield ``{'type':'token','text':..}`` and ``{'type':'tool','name':..}`` dicts.

    Runs a bounded tool-calling loop when tools are supplied and the model
    returns function calls.
    """
    import json as _json

    client = get_client()
    models = [settings.chat_model]
    if settings.chat_fallback_model and settings.chat_fallback_model != settings.chat_model:
        models.append(settings.chat_fallback_model)

    gemini_tools = (
        _build_tools(tools) if (tools and settings.enable_tools) else None
    )

    for round_ in range(max_rounds + 1):
        use_tools = (
            gemini_tools if (gemini_tools and tool_runner and round_ < max_rounds) else None
        )
        system_instruction, contents = _build_contents(messages)

        cfg_kwargs: dict = {}
        if system_instruction:
            cfg_kwargs["system_instruction"] = system_instruction
        if use_tools:
            cfg_kwargs["tools"] = use_tools
        config = types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None

        produced = False
        full_text = ""
        function_calls: list = []

        for attempt, model in enumerate(models):
            try:
                stream = await client.aio.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                )
                async for chunk in stream:
                    for part in (
                        chunk.candidates[0].content.parts
                        if chunk.candidates else []
                    ):
                        if hasattr(part, "text") and part.text:
                            full_text += part.text
                            produced = True
                            yield {"type": "token", "text": part.text}
                        elif hasattr(part, "function_call") and part.function_call:
                            function_calls.append(part.function_call)
                break  # success – skip fallback
            except (ClientError, APIError) as e:
                if produced or attempt + 1 >= len(models):
                    raise translate_error(e) from e
                log.warning(
                    "Model %s failed (%s); trying fallback", model, type(e).__name__
                )

        if not function_calls:
            return

        # ── tool-calling round ───────────────────────────────────────────────
        messages.append({
            "role": "assistant",
            "content": full_text or None,
            "tool_calls": [
                {
                    "id": fc.name,
                    "type": "function",
                    "function": {
                        "name": fc.name,
                        "arguments": _json.dumps(dict(fc.args)),
                    },
                }
                for fc in function_calls
            ],
        })

        for fc in function_calls:
            yield {"type": "tool", "name": fc.name}
            try:
                result = await tool_runner(fc.name, _json.dumps(dict(fc.args)))
            except AIUnavailable as e:
                result = f"Tool failed: {e}"
            messages.append({
                "role": "tool",
                "tool_call_id": fc.name,
                "content": result[:12000],
            })

        # reset accumulators for next round
        full_text = ""
        function_calls = []


async def complete(messages: list[dict], model: str | None = None) -> str:
    """Non-streaming single completion (summarisation, OCR vision, etc.)."""
    client = get_client()
    system_instruction, contents = _build_contents(messages)
    cfg_kwargs: dict = {}
    if system_instruction:
        cfg_kwargs["system_instruction"] = system_instruction
    config = types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None
    try:
        resp = await client.aio.models.generate_content(
            model=model or settings.chat_model,
            contents=contents,
            config=config,
        )
        return (resp.text or "").strip()
    except (ClientError, APIError) as e:
        raise translate_error(e) from e


async def embed(texts: list[str]) -> np.ndarray:
    """Return an L2-normalised float32 matrix of shape ``(len(texts), dim)``."""
    client = get_client()
    out: list[list[float]] = []
    try:
        for text in texts:
            resp = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=text.replace("\n", " ")[:8000],
            )
            out.append(resp.embeddings[0].values)
    except (ClientError, APIError) as e:
        raise translate_error(e) from e
    arr = np.asarray(out, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-9, None)


async def transcribe(
    data: bytes, filename: str, content_type: str, language: str | None
) -> str:
    """Speech-to-text is not available — Gemini has no STT API."""
    raise AIUnavailable(
        "Speech-to-text is not available in Gemini mode. "
        "Audio transcription requires a provider that supports STT."
    )


async def synthesize(text: str, voice: str) -> bytes:
    """Text-to-speech is not available — Gemini has no TTS API."""
    raise AIUnavailable(
        "Text-to-speech is not available in Gemini mode. "
        "Audio synthesis requires a provider that supports TTS."
    )
