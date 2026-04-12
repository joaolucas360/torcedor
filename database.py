from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("torcedor.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id INTEGER PRIMARY KEY,
                team_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_state (
                chat_id INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def salvar_time(chat_id: int, team_id: int, team_name: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO subscriptions (chat_id, team_id, team_name)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                team_id = excluded.team_id,
                team_name = excluded.team_name
            """,
            (chat_id, team_id, team_name),
        )


def obter_time(chat_id: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT team_id, team_name FROM subscriptions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    return {"team_id": row["team_id"], "team_name": row["team_name"]}


def remover_time(chat_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
    return cur.rowcount > 0


def listar_todos_usuarios() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT chat_id, team_id, team_name FROM subscriptions").fetchall()
    return [{"chat_id": row["chat_id"], "team_id": row["team_id"], "team_name": row["team_name"]} for row in rows]


def obter_estado_jogo(chat_id: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM live_state WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["state_json"])
    except Exception:
        return None


def salvar_estado_jogo(chat_id: int, state: dict) -> None:
    state_json = json.dumps(state, ensure_ascii=False)
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO live_state (chat_id, state_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (chat_id, state_json),
        )
