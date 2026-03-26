"""ORM-модели SQLAlchemy для хранения диалогов, сообщений и суммаризаций."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


class Conversation(Base):
    """Диалог с пользователем."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="Новый диалог")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    # Связи: каскадное удаление сообщений и суммаризаций при удалении диалога
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    summaries: Mapped[list["Summary"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """Сообщение в диалоге (от пользователя, ассистента или системы)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Summary(Base):
    """Суммаризация блока старых сообщений для управления контекстом."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    summary: Mapped[str] = mapped_column(Text)
    start_message_id: Mapped[int] = mapped_column(Integer)
    end_message_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="summaries")
