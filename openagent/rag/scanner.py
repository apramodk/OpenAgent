"""Codebase scanner for RAG ingestion."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from openagent.rag.store import Chunk, ChunkMetadata


# File extensions to scan by language
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "rust": [".rs"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "go": [".go"],
    "java": [".java"],
    "csharp": [".cs"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".h"],
    "c": [".c", ".h"],
    "ruby": [".rb"],
    "php": [".php"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "scala": [".scala"],
    "shell": [".sh", ".bash"],
    "sql": [".sql"],
    "yaml": [".yaml", ".yml"],
    "json": [".json"],
    "markdown": [".md"],
    "toml": [".toml"],
}

# Directories to skip
SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "vendor", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "target", "build", "dist", "out",
    ".idea", ".vscode",
    "coverage", ".coverage",
}

# Files to skip
SKIP_FILES = {
    ".gitignore", ".dockerignore",
    "package-lock.json", "yarn.lock", "Cargo.lock",
}


@dataclass
class CodeUnit:
    """A unit of code (function, class, method)."""
    name: str
    unit_type: str  # function, class, method
    signature: str
    docstring: str
    start_line: int
    end_line: int
    calls: list[str] = field(default_factory=list)


@dataclass
class FileAnalysis:
    """Analysis result for a single file."""
    path: str
    language: str
    content: str
    imports: list[str] = field(default_factory=list)
    units: list[CodeUnit] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)


class CodebaseScanner:
    """Scans a codebase and extracts semantic information."""

    def __init__(
        self,
        root_path: Path | str,
        skip_dirs: set[str] | None = None,
        skip_files: set[str] | None = None,
    ):
        self.root_path = Path(root_path).resolve()
        self.skip_dirs = skip_dirs or SKIP_DIRS
        self.skip_files = skip_files or SKIP_FILES

    def scan(self) -> Iterator[FileAnalysis]:
        """Scan the codebase and yield file analyses."""
        for file_path in self._walk_files():
            try:
                analysis = self._analyze_file(file_path)
                if analysis:
                    yield analysis
            except Exception as e:
                # Skip files that can't be analyzed
                print(f"Warning: Could not analyze {file_path}: {e}")
                continue

    def _walk_files(self) -> Iterator[Path]:
        """Walk the directory tree and yield code files."""
        for path in self.root_path.rglob("*"):
            if path.is_file():
                # Skip if in a skip directory
                if any(skip in path.parts for skip in self.skip_dirs):
                    continue

                # Skip specific files
                if path.name in self.skip_files:
                    continue

                # Check if it's a code file
                if self._get_language(path):
                    yield path

    def _get_language(self, path: Path) -> str | None:
        """Get the language for a file based on extension."""
        suffix = path.suffix.lower()
        for lang, extensions in LANGUAGE_EXTENSIONS.items():
            if suffix in extensions:
                return lang
        return None

    def _analyze_file(self, path: Path) -> FileAnalysis | None:
        """Analyze a single file."""
        language = self._get_language(path)
        if not language:
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        # Skip very large files or empty files
        if len(content) > 500_000 or len(content) < 10:
            return None

        relative_path = str(path.relative_to(self.root_path))

        analysis = FileAnalysis(
            path=relative_path,
            language=language,
            content=content,
        )

        # Language-specific analysis
        if language == "python":
            self._analyze_python(analysis, content)
        elif language in ("javascript", "typescript"):
            self._analyze_js_ts(analysis, content)
        elif language == "rust":
            self._analyze_rust(analysis, content)
        else:
            # Basic analysis for other languages
            self._analyze_generic(analysis, content)

        return analysis

    def _analyze_python(self, analysis: FileAnalysis, content: str) -> None:
        """Analyze Python file using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    analysis.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    analysis.imports.append(node.module)

        # Extract classes and functions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                docstring = ast.get_docstring(node) or ""
                analysis.units.append(CodeUnit(
                    name=node.name,
                    unit_type="class",
                    signature=f"class {node.name}",
                    docstring=docstring,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                ))

                # Extract methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_doc = ast.get_docstring(item) or ""
                        args = ", ".join(arg.arg for arg in item.args.args)
                        analysis.units.append(CodeUnit(
                            name=f"{node.name}.{item.name}",
                            unit_type="method",
                            signature=f"def {item.name}({args})",
                            docstring=method_doc,
                            start_line=item.lineno,
                            end_line=item.end_lineno or item.lineno,
                        ))

            elif isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node) or ""
                args = ", ".join(arg.arg for arg in node.args.args)
                analysis.units.append(CodeUnit(
                    name=node.name,
                    unit_type="function",
                    signature=f"def {node.name}({args})",
                    docstring=docstring,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                ))

        # Extract concepts from docstrings and comments
        self._extract_concepts(analysis, content)

    def _analyze_js_ts(self, analysis: FileAnalysis, content: str) -> None:
        """Basic analysis for JavaScript/TypeScript."""
        # Extract imports
        import_pattern = r'(?:import|require)\s*\(?[\'"]([^"\']+)[\'"]'
        for match in re.finditer(import_pattern, content):
            analysis.imports.append(match.group(1))

        # Extract functions and classes (basic regex)
        func_pattern = r'(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s*)?\([^)]*\)\s*=>|\([^)]*\))'
        for match in re.finditer(func_pattern, content):
            analysis.units.append(CodeUnit(
                name=match.group(1),
                unit_type="function",
                signature=match.group(0)[:100],
                docstring="",
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
            ))

        class_pattern = r'class\s+(\w+)'
        for match in re.finditer(class_pattern, content):
            analysis.units.append(CodeUnit(
                name=match.group(1),
                unit_type="class",
                signature=f"class {match.group(1)}",
                docstring="",
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
            ))

        self._extract_concepts(analysis, content)

    def _analyze_rust(self, analysis: FileAnalysis, content: str) -> None:
        """Basic analysis for Rust."""
        # Extract use statements
        use_pattern = r'use\s+([^;]+);'
        for match in re.finditer(use_pattern, content):
            analysis.imports.append(match.group(1).strip())

        # Extract functions
        fn_pattern = r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(<[^>]*>)?\s*\([^)]*\)'
        for match in re.finditer(fn_pattern, content):
            analysis.units.append(CodeUnit(
                name=match.group(1),
                unit_type="function",
                signature=match.group(0)[:100],
                docstring="",
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
            ))

        # Extract structs and enums
        struct_pattern = r'(?:pub\s+)?(?:struct|enum)\s+(\w+)'
        for match in re.finditer(struct_pattern, content):
            analysis.units.append(CodeUnit(
                name=match.group(1),
                unit_type="struct",
                signature=match.group(0),
                docstring="",
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
            ))

        # Extract impl blocks
        impl_pattern = r'impl(?:<[^>]*>)?\s+(\w+)'
        for match in re.finditer(impl_pattern, content):
            analysis.units.append(CodeUnit(
                name=match.group(1),
                unit_type="impl",
                signature=match.group(0),
                docstring="",
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
            ))

        self._extract_concepts(analysis, content)

    def _analyze_generic(self, analysis: FileAnalysis, content: str) -> None:
        """Generic analysis for other languages."""
        # Just extract concepts
        self._extract_concepts(analysis, content)

    def _extract_concepts(self, analysis: FileAnalysis, content: str) -> None:
        """Extract concept keywords from content."""
        # Common concept patterns
        concept_patterns = [
            r'\b(auth(?:entication|orization)?)\b',
            r'\b(api|rest|graphql|grpc)\b',
            r'\b(database|db|sql|query)\b',
            r'\b(cache|caching|redis|memcache)\b',
            r'\b(test(?:ing)?|spec|unittest)\b',
            r'\b(config(?:uration)?|settings?|env)\b',
            r'\b(log(?:ging)?|logger|debug)\b',
            r'\b(error|exception|handler)\b',
            r'\b(async|await|promise|future)\b',
            r'\b(http|request|response|client|server)\b',
            r'\b(parse|serialize|deserialize|json|xml)\b',
            r'\b(encrypt|decrypt|hash|security)\b',
            r'\b(route|router|endpoint|handler)\b',
            r'\b(model|schema|entity|dto)\b',
            r'\b(service|repository|controller)\b',
            r'\b(middleware|interceptor|filter)\b',
            r'\b(event|listener|subscriber|publish)\b',
            r'\b(queue|worker|job|task)\b',
            r'\b(file|stream|io|read|write)\b',
            r'\b(user|session|token|jwt)\b',
        ]

        concepts = set()
        content_lower = content.lower()
        for pattern in concept_patterns:
            if re.search(pattern, content_lower):
                match = re.search(pattern, content_lower)
                if match:
                    concepts.add(match.group(1))

        analysis.concepts = list(concepts)[:10]  # Limit to 10 concepts


def analysis_to_chunks(analysis: FileAnalysis) -> list[Chunk]:
    """Convert a FileAnalysis to RAG chunks."""
    chunks = []

    # File-level chunk
    file_desc = f"{analysis.path}: "
    if analysis.units:
        unit_names = [u.name for u in analysis.units[:5]]
        file_desc += f"Contains {', '.join(unit_names)}"
        if len(analysis.units) > 5:
            file_desc += f" and {len(analysis.units) - 5} more"
    else:
        file_desc += f"{analysis.language} file"

    if analysis.concepts:
        file_desc += f". Concepts: {', '.join(analysis.concepts)}"

    chunks.append(Chunk(
        id=analysis.path,
        content=file_desc,
        metadata=ChunkMetadata(
            path=analysis.path,
            language=analysis.language,
            chunk_type="file",
            concepts=analysis.concepts,
        ),
    ))

    # Code unit chunks
    for unit in analysis.units:
        unit_id = f"{analysis.path}:{unit.name}"
        unit_desc = f"{unit.name}: "

        if unit.docstring:
            # Use docstring as description
            unit_desc += unit.docstring.split('\n')[0][:200]
        else:
            unit_desc += f"{unit.unit_type} in {analysis.path}"

        chunks.append(Chunk(
            id=unit_id,
            content=unit_desc,
            metadata=ChunkMetadata(
                path=analysis.path,
                chunk_type=unit.unit_type,
                signature=unit.signature,
                calls=unit.calls,
            ),
        ))

    return chunks


def scan_and_generate_chunks(
    root_path: Path | str,
    skip_dirs: set[str] | None = None,
) -> tuple[list[Chunk], dict]:
    """
    Scan a codebase and generate RAG chunks.

    Returns:
        Tuple of (chunks, stats)
    """
    scanner = CodebaseScanner(root_path, skip_dirs=skip_dirs)

    all_chunks = []
    stats = {
        "files_scanned": 0,
        "files_by_language": {},
        "units_extracted": 0,
        "chunks_generated": 0,
    }

    for analysis in scanner.scan():
        stats["files_scanned"] += 1
        stats["files_by_language"][analysis.language] = (
            stats["files_by_language"].get(analysis.language, 0) + 1
        )
        stats["units_extracted"] += len(analysis.units)

        chunks = analysis_to_chunks(analysis)
        all_chunks.extend(chunks)

    stats["chunks_generated"] = len(all_chunks)
    return all_chunks, stats
