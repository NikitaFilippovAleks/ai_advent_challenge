"""ORM-модели SQLAlchemy для хранения диалогов, сообщений, суммаризаций, фактов, веток, памяти и индекса документов."""

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
    # Профиль пользователя (system prompt)
    profile_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )

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
    insights: Mapped[list["ShortTermInsight"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
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
    # Категория рабочей памяти: fact, goal, constraint, decision, result
    category: Mapped[str] = mapped_column(String, default="fact")
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


class ShortTermInsight(Base):
    """Краткосрочная память — ключевые наблюдения из текущего диалога."""

    __tablename__ = "short_term_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(Text)
    # ID сообщения, из которого извлечено наблюдение (информационно)
    source_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="insights")


class LongTermMemory(Base):
    """Долгосрочная память — кросс-диалоговая, не привязана к конкретному диалогу."""

    __tablename__ = "long_term_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Категория: preference, knowledge, decision
    category: Mapped[str] = mapped_column(String)
    key: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(Text)
    # Информационная ссылка на диалог-источник (без FK — не удаляется при удалении диалога)
    source_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class UserProfile(Base):
    """Профиль пользователя — набор инструкций для LLM (system prompt)."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class Invariant(Base):
    """Инвариант — правило, которое ассистент не имеет права нарушать."""

    __tablename__ = "invariants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Категория: architecture, technical, stack, business
    category: Mapped[str] = mapped_column(String, default="business")
    is_active: Mapped[bool] = mapped_column(Integer, default=1)
    # Приоритет (выше число = важнее)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class Task(Base):
    """Задача с конечным автоматом состояний."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    phase: Mapped[str] = mapped_column(String, default="planning")
    previous_phase: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, default="")
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    status_text: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    conversation: Mapped["Conversation"] = relationship(back_populates="tasks")


class IndexedDocument(Base):
    """Проиндексированный документ."""

    __tablename__ = "indexed_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    chunking_strategy: Mapped[str] = mapped_column(String, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Чанк документа с эмбеддингом и метаданными."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("indexed_documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Эмбеддинг в формате JSON-массива float[]
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Метаданные чанка
    source: Mapped[str] = mapped_column(String)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String)

    document: Mapped["IndexedDocument"] = relationship(back_populates="chunks")
