"""Conversation history storage."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from secondbrain.models import Conversation, ConversationMessage


class ConversationStore:
    """SQLite-based conversation history storage."""

    def __init__(self, db_path: Path, max_messages: int = 20) -> None:
        """Initialize the conversation store.

        Args:
            db_path: Path to the SQLite database file.
            max_messages: Maximum messages to keep per conversation.
        """
        self.db_path = db_path
        self.max_messages = max_messages
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id);
        """)
        self.conn.commit()

    def create_conversation(self) -> str:
        """Create a new conversation.

        Returns:
            The new conversation ID.
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        self.conn.execute(
            "INSERT INTO conversations (conversation_id, created_at, updated_at) VALUES (?, ?, ?)",
            (conversation_id, now, now),
        )
        self.conn.commit()

        return conversation_id

    def get_or_create_conversation(self, conversation_id: str | None) -> str:
        """Get an existing conversation or create a new one.

        Args:
            conversation_id: Optional existing conversation ID.

        Returns:
            The conversation ID (existing or new).
        """
        if conversation_id:
            cursor = self.conn.execute(
                "SELECT conversation_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            if cursor.fetchone():
                return conversation_id

        return self.create_conversation()

    def add_message(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        """Add a message to a conversation.

        Args:
            conversation_id: The conversation ID.
            role: Message role ("user" or "assistant").
            content: Message content.
        """
        now = datetime.utcnow().isoformat()

        self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        self.conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
            (now, conversation_id),
        )
        self.conn.commit()

        # Prune old messages if needed
        self._prune_messages(conversation_id)

    def _prune_messages(self, conversation_id: str) -> None:
        """Keep only the most recent messages."""
        self.conn.execute(
            """
            DELETE FROM messages
            WHERE conversation_id = ?
            AND id NOT IN (
                SELECT id FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (conversation_id, conversation_id, self.max_messages),
        )
        self.conn.commit()

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get a conversation with its messages.

        Args:
            conversation_id: The conversation ID.

        Returns:
            The Conversation object, or None if not found.
        """
        cursor = self.conn.execute(
            "SELECT conversation_id FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        if not cursor.fetchone():
            return None

        cursor = self.conn.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        )

        messages = [
            ConversationMessage(role=row["role"], content=row["content"])
            for row in cursor.fetchall()
        ]

        return Conversation(conversation_id=conversation_id, messages=messages)

    def get_recent_messages(
        self, conversation_id: str, limit: int = 10
    ) -> list[ConversationMessage]:
        """Get the most recent messages from a conversation.

        Args:
            conversation_id: The conversation ID.
            limit: Maximum number of messages to return.

        Returns:
            List of messages, oldest first.
        """
        cursor = self.conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, id FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (conversation_id, limit),
        )

        return [
            ConversationMessage(role=row["role"], content=row["content"])
            for row in cursor.fetchall()
        ]

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and all its messages."""
        self.conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        self.conn.execute(
            "DELETE FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
