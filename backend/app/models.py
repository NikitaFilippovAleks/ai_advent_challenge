"""ORM-модели SQLAlchemy для хранения диалогов, сообщений, суммаризаций, фактов и веток."""

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
    # Стратегия управления контекстом: summary, sliding_window, sticky_facts, branching
    context_strategy: Mapped[str] = mapped_column(String, default="summary")
    # Активная ветка (для стратегии branching)
    active_branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Связи: каскадное удаление при удалении диалога
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    summaries: Mapped[list["Summary"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    facts: Mapped[list["ConversationFact"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    branches: Mapped[list["Branch"]] = relationship(
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
    # ID ветки (для стратегии branching, NULL = основная линия)
    branch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("branches.id"), nullable=True)

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


class ConversationFact(Base):
    """Ключевой факт из диалога (для стратегии Sticky Facts)."""

    __tablename__ = "conversation_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="facts")


class Branch(Base):
    """Ветка диалога (для стратегии Branching)."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String)
    # ID сообщения, от которого ветка отходит (чекпоинт)
    checkpoint_message_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="branches")
