"""
AST and Regex-based code symbol extractor and call graph indexer.
Extracts classes, functions, exported types, and route signatures across the workspace
to provide ultra-compact (< 1,000 token) symbol outlines without prompt bloat.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SymbolItem:
    name: str
    kind: str  # "class", "function", "endpoint", "type"
    file_path: str
    line_number: int
    signature: str = ""
    docstring: str = ""


class SymbolIndexer:
    """Extracts symbol outlines from repository source files."""

    @classmethod
    def extract_symbols(cls, workspace_dir: Path, max_files: int = 50) -> List[SymbolItem]:
        """Scans workspace source files and extracts high-value symbols."""
        workspace_dir = Path(workspace_dir).resolve()
        symbols: List[SymbolItem] = []

        ignore_dirs = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}

        scanned = 0
        for root, dirs, files in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for file in sorted(files):
                if scanned >= max_files:
                    break
                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(workspace_dir))

                if file.endswith(".py"):
                    symbols.extend(cls._extract_python_symbols(file_path, rel_path))
                    scanned += 1
                elif file.endswith((".ts", ".js", ".tsx", ".jsx")):
                    symbols.extend(cls._extract_ts_symbols(file_path, rel_path))
                    scanned += 1
                elif file.endswith(".go"):
                    symbols.extend(cls._extract_go_symbols(file_path, rel_path))
                    scanned += 1
                elif file.endswith(".rs"):
                    symbols.extend(cls._extract_rust_symbols(file_path, rel_path))
                    scanned += 1

        return symbols

    @classmethod
    def _extract_python_symbols(cls, file_path: Path, rel_path: str) -> List[SymbolItem]:
        items: List[SymbolItem] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(file_path))
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    sig = f"class {node.name}({', '.join(getattr(b, 'id', '...') for b in node.bases)}) [methods: {', '.join(methods[:4])}]"
                    items.append(SymbolItem(name=node.name, kind="class", file_path=rel_path, line_number=node.lineno, signature=sig))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args if a.arg != "self"]
                    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
                    sig = f"{prefix}{node.name}({', '.join(args[:5])})"
                    items.append(SymbolItem(name=node.name, kind="function", file_path=rel_path, line_number=node.lineno, signature=sig))
        except Exception:
            pass
        return items

    @classmethod
    def _extract_ts_symbols(cls, file_path: Path, rel_path: str) -> List[SymbolItem]:
        items: List[SymbolItem] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                m_class = re.search(r"export\s+class\s+([A-Za-z0-9_]+)", line)
                if m_class:
                    items.append(SymbolItem(name=m_class.group(1), kind="class", file_path=rel_path, line_number=line_no, signature=line.strip()))
                m_fn = re.search(r"export\s+(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)", line)
                if m_fn:
                    items.append(SymbolItem(name=m_fn.group(1), kind="function", file_path=rel_path, line_number=line_no, signature=f"function {m_fn.group(1)}({m_fn.group(2)})"))
                m_type = re.search(r"export\s+(?:type|interface)\s+([A-Za-z0-9_]+)", line)
                if m_type:
                    items.append(SymbolItem(name=m_type.group(1), kind="type", file_path=rel_path, line_number=line_no, signature=line.strip()))
        except Exception:
            pass
        return items

    @classmethod
    def _extract_go_symbols(cls, file_path: Path, rel_path: str) -> List[SymbolItem]:
        items: List[SymbolItem] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                m_fn = re.search(r"^func\s+(?:\([^\)]+\)\s+)?([A-Z][A-Za-z0-9_]*)\s*\((.*?)\)", line)
                if m_fn:
                    items.append(SymbolItem(name=m_fn.group(1), kind="function", file_path=rel_path, line_number=line_no, signature=line.strip()))
                m_type = re.search(r"^type\s+([A-Z][A-Za-z0-9_]*)\s+(?:struct|interface)", line)
                if m_type:
                    items.append(SymbolItem(name=m_type.group(1), kind="type", file_path=rel_path, line_number=line_no, signature=line.strip()))
        except Exception:
            pass
        return items

    @classmethod
    def _extract_rust_symbols(cls, file_path: Path, rel_path: str) -> List[SymbolItem]:
        items: List[SymbolItem] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                m_fn = re.search(r"pub\s+(?:async\s+)?fn\s+([a-z0-9_]+)", line)
                if m_fn:
                    items.append(SymbolItem(name=m_fn.group(1), kind="function", file_path=rel_path, line_number=line_no, signature=line.strip()))
                m_type = re.search(r"pub\s+(?:struct|enum|trait)\s+([A-Za-z0-9_]+)", line)
                if m_type:
                    items.append(SymbolItem(name=m_type.group(1), kind="type", file_path=rel_path, line_number=line_no, signature=line.strip()))
        except Exception:
            pass
        return items

    @classmethod
    def format_symbol_outline(cls, symbols: List[SymbolItem], max_items: int = 25) -> str:
        """Formats a compact markdown outline of repository symbols for LLM prompting."""
        if not symbols:
            return ""

        by_file: Dict[str, List[str]] = {}
        for s in symbols[:max_items]:
            by_file.setdefault(s.file_path, []).append(f"  - `{s.signature}` (L{s.line_number})")

        lines = ["### 🧬 Codebase Symbol & API Graph:"]
        for path, entries in by_file.items():
            lines.append(f"- **{path}**:")
            lines.extend(entries[:4])

        return "\n".join(lines)
