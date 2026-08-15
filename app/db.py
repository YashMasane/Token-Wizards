import sqlite3
import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

def get_db_connection():
    db_path = settings.SQLITE_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logger.info(f"Initializing SQLite database at {settings.SQLITE_DB_PATH}...")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Threads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    
    # Messages table for sliding window chat history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (thread_id) REFERENCES threads (thread_id)
        )
    """)
    
    # Corpus registry table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS corpus_registry (
            doc_id TEXT PRIMARY KEY,
            document_name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            issuing_authority TEXT,
            doc_date TEXT,
            is_outdated BOOLEAN,
            download_url TEXT,
            raw_content TEXT,
            created_at TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def save_thread(thread_id: str, title: str = "New Legal Consultation"):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO threads (thread_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET updated_at = ?
    """, (thread_id, title, now, now, now))
    conn.commit()
    conn.close()

def save_message(thread_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
    save_thread(thread_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    cursor.execute("""
        INSERT INTO messages (thread_id, role, content, metadata_json, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (thread_id, role, content, meta_json, now))
    conn.commit()
    conn.close()
    logger.info(f"[DB] Saved '{role}' message for thread '{thread_id}' ({len(content)} chars)")

def get_sliding_window_messages(thread_id: str, limit: int = None) -> List[Dict[str, Any]]:
    if limit is None:
        limit = settings.SLIDING_WINDOW_SIZE
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, metadata_json, timestamp FROM messages
        WHERE thread_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (thread_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for r in reversed(rows):
        messages.append({
            "role": r["role"],
            "content": r["content"],
            "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else {},
            "timestamp": r["timestamp"]
        })
    logger.info(f"[DB] Fetched sliding window history for thread '{thread_id}': {len(messages)} messages (Limit: {limit})")
    return messages

def register_corpus_document(doc_data: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    doc_id = doc_data["doc_id"]
    cursor.execute("""
        INSERT INTO corpus_registry (doc_id, document_name, doc_type, issuing_authority, doc_date, is_outdated, download_url, raw_content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            document_name = excluded.document_name,
            doc_type = excluded.doc_type,
            issuing_authority = excluded.issuing_authority,
            doc_date = excluded.doc_date,
            is_outdated = excluded.is_outdated,
            download_url = excluded.download_url,
            raw_content = excluded.raw_content,
            created_at = excluded.created_at
    """, (
        doc_id,
        doc_data["document_name"],
        doc_data["doc_type"],
        doc_data.get("issuing_authority", ""),
        doc_data.get("date", ""),
        doc_data.get("is_outdated", False),
        doc_data.get("download_url", ""),
        json.dumps(doc_data),
        now
    ))
    conn.commit()
    conn.close()
    logger.info(f"[DB] Registered document '{doc_id}' ({doc_data.get('document_name')}) in corpus registry.")


def get_all_registered_documents() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT doc_id, document_name, doc_type, issuing_authority, doc_date, is_outdated, download_url FROM corpus_registry")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_threads() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.thread_id, t.title, t.updated_at,
               (SELECT content FROM messages m WHERE m.thread_id = t.thread_id AND m.role = 'user' ORDER BY id ASC LIMIT 1) as first_message
        FROM threads t
        ORDER BY t.updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    threads = []
    for r in rows:
        title = r["title"]
        if title == "New Legal Consultation" and r["first_message"]:
            first_msg = r["first_message"].strip()
            title = first_msg[:30] + "..." if len(first_msg) > 30 else first_msg
            
        threads.append({
            "thread_id": r["thread_id"],
            "title": title,
            "updated_at": r["updated_at"]
        })
    return threads

