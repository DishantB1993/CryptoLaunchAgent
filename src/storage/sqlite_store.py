"""
Simple SQLite-backed persistence for launches, scores, trades, and positions.

This is intentionally minimal: it creates tables and exposes basic save
methods. It is suitable for paper-trading and local development.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteStore:
    """Lightweight wrapper around SQLite used for local persistence."""

    def __init__(self, db_path: str | Path = "data/agent.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_schema(self) -> None:
        """Create minimal tables for tokens, pairs, scores, trades, positions."""
        if not self.conn:
            self.connect()
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                address TEXT PRIMARY KEY,
                name TEXT,
                symbol TEXT,
                decimals INTEGER,
                metadata TEXT,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pairs (
                address TEXT PRIMARY KEY,
                token0 TEXT,
                token1 TEXT,
                liquidity REAL,
                created_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT,
                score REAL,
                reasons TEXT,
                confidence REAL,
                computed_at TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                token_address TEXT,
                side TEXT,
                amount REAL,
                price REAL,
                simulated INTEGER,
                timestamp TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                token_address TEXT PRIMARY KEY,
                amount REAL,
                entry_price REAL,
                pnl REAL,
                opened_at TEXT,
                closed_at TEXT
            )
            """
        )
        self.conn.commit()

    # Minimal save methods (placeholders)
    def save_token(self, address: str, **kwargs) -> None:
        if not self.conn:
            self.connect()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO tokens (address, name, symbol, decimals, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                address,
                kwargs.get("name"),
                kwargs.get("symbol"),
                kwargs.get("decimals"),
                kwargs.get("metadata"),
                kwargs.get("created_at"),
            ),
        )
        self.conn.commit()

    def save_score(self, token_address: str, score: float, reasons: str, confidence: float, computed_at: str) -> None:
        if not self.conn:
            self.connect()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO scores (token_address, score, reasons, confidence, computed_at) VALUES (?, ?, ?, ?, ?)",
            (token_address, score, reasons, confidence, computed_at),
        )
        self.conn.commit()


__all__ = ["SQLiteStore"]
