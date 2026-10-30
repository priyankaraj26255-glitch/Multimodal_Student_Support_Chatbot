from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Lang = Literal["auto", "en", "hi", "mr"]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    display_name: Optional[str] = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def _bytes(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class FileOut(BaseModel):
    id: str
    kind: str
    filename: str
    mime_type: str
    size_bytes: int
    page_count: Optional[int] = None
    status: str
    warning: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    has_text: bool = False
    created_at: datetime

    @classmethod
    def from_model(cls, f) -> "FileOut":
        return cls(id=f.id, kind=f.kind, filename=f.filename, mime_type=f.mime_type,
                   size_bytes=f.size_bytes, page_count=f.page_count, status=f.status,
                   warning=f.warning, conversation_id=f.conversation_id,
                   message_id=f.message_id, has_text=bool(f.extracted_text),
                   created_at=f.created_at)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: Optional[list] = None
    attachments: list[FileOut] = []
    created_at: datetime

    @classmethod
    def from_model(cls, m) -> "MessageOut":
        return cls(id=m.id, role=m.role, content=m.content, sources=m.sources,
                   attachments=[FileOut.from_model(f) for f in m.files],
                   created_at=m.created_at)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    language: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", max_length=200)
    language: Optional[Lang] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    language: Optional[Lang] = None


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=6)
    language: Optional[Lang] = None
    input_mode: Literal["text", "voice"] = "text"


class DocQueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    file_ids: list[str] = Field(min_length=1, max_length=10)
    language: Lang = "auto"


class DocGenerateIn(BaseModel):
    mode: Literal["summary", "quiz", "flashcards", "notes", "compare"]
    file_ids: list[str] = Field(min_length=1, max_length=10)
    language: Lang = "auto"


class OCRIn(BaseModel):
    engine: Literal["auto", "tesseract", "vision"] = "auto"


class TextIn(BaseModel):
    text: str = Field(max_length=200000)


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    voice: Optional[str] = None


class PreferencesIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    language: Lang = "auto"
    personalization_enabled: bool = False
    about_me: str = Field(default="", max_length=2000)
    tts_voice: str = "alloy"
    auto_speak: bool = False
