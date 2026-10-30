import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User, UserPreference
from ..ratelimit import ai_limiter
from ..schemas import SpeechIn
from ..security import get_current_user
from ..services import llm, storage

settings = get_settings()
router = APIRouter(prefix="/audio", tags=["audio"], dependencies=[Depends(ai_limiter)])
EXT = {"audio/webm": "webm", "video/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/m4a": "m4a",
       "audio/x-m4a": "m4a", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
       "audio/wave": "wav", "audio/flac": "flac"}
VOICES = {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*[#>*\-|]+\s*", "", text, flags=re.M)
    text = re.sub(r"[*_~|]", "", text)
    return re.sub(r"\n{2,}", "\n", text).strip()[:4000]


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str | None = Form(None),
                     user: User = Depends(get_current_user)):
    ctype = (audio.content_type or "").split(";")[0].strip().lower()
    if ctype not in EXT:
        raise HTTPException(415, "Unsupported audio format. Use WEBM, OGG, MP4/M4A, MP3, WAV or FLAC.")
    if language and language not in ("auto", "en", "hi", "mr"):
        raise HTTPException(422, "Unsupported language.")
    data = await storage.read_limited(audio, settings.max_audio_mb * storage.MB)
    text = await llm.transcribe(data, f"speech.{EXT[ctype]}", ctype, language)
    if not text:
        raise HTTPException(422, "No speech was detected. Please try again, speaking closer to the microphone.")
    return {"text": text}


@router.post("/speech")
async def speech(data: SpeechIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = clean_for_speech(data.text)
    if not text:
        raise HTTPException(422, "There is no speakable text in this message.")
    prefs = db.get(UserPreference, user.id)
    voice = data.voice or (prefs.tts_voice if prefs else settings.tts_voice)
    if voice not in VOICES:
        voice = settings.tts_voice
    audio = await llm.synthesize(text, voice)
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
