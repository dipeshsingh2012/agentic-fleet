"""
Unit tests for code symbol extraction and compact outline generation.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from src.symbol_indexer import SymbolIndexer


def test_extract_python_and_ts_symbols(tmp_path: Path):
    py_file = tmp_path / "service.py"
    py_file.write_text(
        "class AuthService:\n"
        "    def login(self, username: str):\n"
        "        pass\n\n"
        "def verify_token(token: str):\n"
        "    pass\n"
    )

    ts_file = tmp_path / "client.ts"
    ts_file.write_text(
        "export class ApiClient {}\n"
        "export function fetchData(query: string) {}\n"
        "export interface UserResponse {}\n"
    )

    symbols = SymbolIndexer.extract_symbols(tmp_path)
    assert len(symbols) >= 4

    names = [s.name for s in symbols]
    assert "AuthService" in names
    assert "verify_token" in names
    assert "ApiClient" in names
    assert "fetchData" in names

    outline = SymbolIndexer.format_symbol_outline(symbols)
    assert "### 🧬 Codebase Symbol & API Graph:" in outline
    assert "service.py" in outline
    assert "client.ts" in outline
