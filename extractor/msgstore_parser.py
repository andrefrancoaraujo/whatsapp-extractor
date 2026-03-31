"""
Parse decrypted WhatsApp msgstore.db (SQLite) into structured JSON.
Handles schema differences between WhatsApp versions.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import MESSAGE_TYPES


class ParseError(Exception):
    """Raised when database parsing fails."""
    pass


def _get_columns(cursor, table: str) -> list[str]:
    """Get column names for a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def _detect_text_column(columns: list[str]) -> str:
    """Find the text content column (varies by WhatsApp version)."""
    for candidate in ("text_data", "data", "body"):
        if candidate in columns:
            return candidate
    raise ParseError(
        f"Nao encontrei coluna de texto na tabela message. "
        f"Colunas disponiveis: {columns}"
    )


def _detect_sort_column(columns: list[str]) -> str:
    """Find the sort/order column."""
    for candidate in ("sort_id", "timestamp", "_id"):
        if candidate in columns:
            return candidate
    return "_id"


def _ts_to_datetime(ts_ms: int) -> datetime:
    """Convert WhatsApp timestamp (milliseconds) to datetime."""
    if ts_ms is None or ts_ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (OSError, ValueError):
        return None


def _format_media_placeholder(message_type: int) -> str:
    """Convert message type int to a placeholder string."""
    type_name = MESSAGE_TYPES.get(message_type, "midia")
    return f"[{type_name.capitalize()}]"


def parse_msgstore(db_path: str, progress_callback=None) -> list[dict]:
    """
    Parse a decrypted msgstore.db into conversation dicts.

    Args:
        db_path: Path to decrypted msgstore.db
        progress_callback: Optional fn(current, total, contact_name)

    Returns:
        List of conversation dicts matching server format:
        [{"contact": "...", "message_count": N, "messages": [...], ...}]

    Raises:
        ParseError: If the database structure is unexpected.
    """
    db = Path(db_path)
    if not db.exists():
        raise ParseError(f"Banco de dados nao encontrado: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Validate required tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    for required in ("message", "chat", "jid"):
        if required not in tables:
            raise ParseError(
                f"Tabela '{required}' nao encontrada. "
                f"Este arquivo pode nao ser um backup do WhatsApp."
            )

    # Detect schema
    msg_columns = _get_columns(cursor, "message")
    text_col = _detect_text_column(msg_columns)
    sort_col = _detect_sort_column(msg_columns)
    has_sender_jid = "sender_jid_row_id" in msg_columns
    has_message_type = "message_type" in msg_columns

    # Get all chats
    cursor.execute("""
        SELECT c._id, c.subject, j.raw_string AS jid,
               j.user AS jid_user, j.server AS jid_server
        FROM chat c
        JOIN jid j ON c.jid_row_id = j._id
        WHERE c.hidden = 0 OR c.hidden IS NULL
    """)
    chats = cursor.fetchall()
    total_chats = len(chats)

    conversations = []

    for idx, chat in enumerate(chats):
        chat_id = chat["_id"]
        jid = chat["jid"] or ""
        group_name = chat["subject"]
        is_group = (chat["jid_server"] or "").endswith("g.us")

        # Build display name
        contact_name = group_name if is_group and group_name else jid

        if progress_callback:
            progress_callback(idx + 1, total_chats, contact_name)

        # Build message query dynamically based on available columns
        select_parts = [
            f"m.{text_col} AS text_content",
            "m.from_me",
            "m.timestamp",
        ]
        if has_message_type:
            select_parts.append("m.message_type")
        if has_sender_jid:
            select_parts.append("sj.raw_string AS sender_jid")

        join_parts = ""
        if has_sender_jid:
            join_parts = "LEFT JOIN jid sj ON m.sender_jid_row_id = sj._id"

        query = f"""
            SELECT {', '.join(select_parts)}
            FROM message m
            {join_parts}
            WHERE m.chat_row_id = ?
            ORDER BY m.{sort_col} ASC
        """
        cursor.execute(query, (chat_id,))
        rows = cursor.fetchall()

        if not rows:
            continue

        messages = []
        for row in rows:
            text = row["text_content"]
            msg_type = row["message_type"] if has_message_type else 0
            from_me = bool(row["from_me"])

            # Skip system messages (type 7 = system, no text)
            if msg_type in (7,) and not text:
                continue

            # Build text content
            if msg_type and msg_type != 0 and not text:
                text = _format_media_placeholder(msg_type)
            elif not text:
                continue  # Empty message

            # Parse timestamp
            dt = _ts_to_datetime(row["timestamp"])
            date_str = dt.strftime("%d/%m/%Y") if dt else ""
            time_str = dt.strftime("%H:%M") if dt else ""

            # Sender
            if from_me:
                sender = "Voce"
            elif has_sender_jid and row["sender_jid"]:
                sender = row["sender_jid"]
            else:
                sender = jid

            messages.append({
                "date": date_str,
                "time": time_str,
                "sender": sender,
                "text": text,
                "from_me": from_me,
            })

        if not messages:
            continue

        conversations.append({
            "contact": jid,
            "contact_name": contact_name,
            "is_group": is_group,
            "message_count": len(messages),
            "messages": messages,
            "first_message": messages[0]["date"],
            "last_message": messages[-1]["date"],
        })

    conn.close()

    # Sort by message count descending
    conversations.sort(key=lambda c: c["message_count"], reverse=True)

    return conversations


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python msgstore_parser.py <msgstore.db>")
        sys.exit(1)

    convos = parse_msgstore(
        sys.argv[1],
        progress_callback=lambda cur, tot, name: print(f"  [{cur}/{tot}] {name}")
    )

    total_msgs = sum(c["message_count"] for c in convos)
    print(f"\n{len(convos)} conversas, {total_msgs} mensagens total")

    # Save JSON
    out = Path(sys.argv[1]).with_suffix(".json")
    out.write_text(json.dumps(convos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Salvo em: {out}")
