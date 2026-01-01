"""Built-in tools for common operations.

These tools can be used directly without MCP servers.
They're registered as async handlers in the ToolRegistry.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

from openagent.tools.registry import Tool, ToolRegistry


# ============================================================================
# Filesystem Tools
# ============================================================================

async def read_file(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """
    Read contents of a file.

    Args:
        path: Path to the file
        encoding: File encoding (default: utf-8)

    Returns:
        Dict with content or error
    """
    try:
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return {"error": f"File not found: {path}"}

        if not file_path.is_file():
            return {"error": f"Not a file: {path}"}

        # Check file size (limit to 1MB)
        size = file_path.stat().st_size
        if size > 1_000_000:
            return {"error": f"File too large: {size} bytes (max 1MB)"}

        content = file_path.read_text(encoding=encoding)
        return {
            "content": content,
            "path": str(file_path),
            "size": size,
        }
    except Exception as e:
        return {"error": str(e)}


async def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = False,
) -> dict[str, Any]:
    """
    Write content to a file.

    Args:
        path: Path to the file
        content: Content to write
        encoding: File encoding (default: utf-8)
        create_dirs: Create parent directories if needed

    Returns:
        Dict with success status or error
    """
    try:
        file_path = Path(path).expanduser().resolve()

        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding=encoding)
        return {
            "success": True,
            "path": str(file_path),
            "size": len(content),
        }
    except Exception as e:
        return {"error": str(e)}


async def list_directory(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = False,
) -> dict[str, Any]:
    """
    List files in a directory.

    Args:
        path: Directory path
        pattern: Glob pattern (default: *)
        recursive: Search recursively

    Returns:
        Dict with files list or error
    """
    try:
        dir_path = Path(path).expanduser().resolve()

        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}

        if not dir_path.is_dir():
            return {"error": f"Not a directory: {path}"}

        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))

        # Limit results
        files = files[:1000]

        return {
            "path": str(dir_path),
            "files": [
                {
                    "name": f.name,
                    "path": str(f),
                    "is_dir": f.is_dir(),
                    "size": f.stat().st_size if f.is_file() else 0,
                }
                for f in sorted(files)
            ],
            "count": len(files),
        }
    except Exception as e:
        return {"error": str(e)}


async def search_files(
    path: str,
    pattern: str,
    content_pattern: str | None = None,
) -> dict[str, Any]:
    """
    Search for files by name and optionally content.

    Args:
        path: Directory to search
        pattern: Filename glob pattern
        content_pattern: Optional text to search in files

    Returns:
        Dict with matching files
    """
    try:
        dir_path = Path(path).expanduser().resolve()

        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}

        matches = []
        for file_path in dir_path.rglob(pattern):
            if not file_path.is_file():
                continue

            match_info = {
                "path": str(file_path),
                "name": file_path.name,
            }

            # Search content if pattern provided
            if content_pattern:
                try:
                    content = file_path.read_text(errors="ignore")
                    if content_pattern.lower() in content.lower():
                        # Find matching lines
                        lines = content.split("\n")
                        matching_lines = [
                            (i + 1, line.strip())
                            for i, line in enumerate(lines)
                            if content_pattern.lower() in line.lower()
                        ][:5]  # Limit to 5 matches per file

                        match_info["matches"] = matching_lines
                        matches.append(match_info)
                except Exception:
                    pass
            else:
                matches.append(match_info)

            if len(matches) >= 100:
                break

        return {
            "path": str(dir_path),
            "pattern": pattern,
            "matches": matches,
            "count": len(matches),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Shell Tools
# ============================================================================

async def run_command(
    command: str,
    cwd: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Run a shell command.

    Args:
        command: Command to run
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Dict with stdout, stderr, and return code
    """
    try:
        cwd_path = Path(cwd).expanduser().resolve() if cwd else None

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd_path,
            capture_output=True,
            timeout=timeout,
            text=True,
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Git Tools
# ============================================================================

async def git_status(path: str = ".") -> dict[str, Any]:
    """Get git status for a repository."""
    return await run_command("git status --porcelain", cwd=path)


async def git_diff(path: str = ".", staged: bool = False) -> dict[str, Any]:
    """Get git diff."""
    cmd = "git diff --staged" if staged else "git diff"
    return await run_command(cmd, cwd=path)


async def git_log(path: str = ".", count: int = 10) -> dict[str, Any]:
    """Get recent git commits."""
    cmd = f"git log --oneline -n {count}"
    return await run_command(cmd, cwd=path)


# ============================================================================
# Tool Registration
# ============================================================================

FILESYSTEM_TOOLS = [
    Tool(
        name="read_file",
        description="Read the contents of a file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["path"],
        },
        handler=read_file,
    ),
    Tool(
        name="write_file",
        description="Write content to a file",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"},
                "create_dirs": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
        },
        handler=write_file,
    ),
    Tool(
        name="list_directory",
        description="List files in a directory",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "pattern": {"type": "string", "default": "*"},
                "recursive": {"type": "boolean", "default": False},
            },
        },
        handler=list_directory,
    ),
    Tool(
        name="search_files",
        description="Search for files by name and content",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search"},
                "pattern": {"type": "string", "description": "Filename pattern"},
                "content_pattern": {"type": "string", "description": "Text to search in files"},
            },
            "required": ["path", "pattern"],
        },
        handler=search_files,
    ),
]

SHELL_TOOLS = [
    Tool(
        name="run_command",
        description="Run a shell command",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
                "cwd": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
        handler=run_command,
    ),
]

GIT_TOOLS = [
    Tool(
        name="git_status",
        description="Get git status for a repository",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
            },
        },
        handler=git_status,
    ),
    Tool(
        name="git_diff",
        description="Get git diff",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "staged": {"type": "boolean", "default": False},
            },
        },
        handler=git_diff,
    ),
    Tool(
        name="git_log",
        description="Get recent git commits",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "count": {"type": "integer", "default": 10},
            },
        },
        handler=git_log,
    ),
]


def register_builtin_tools(registry: ToolRegistry, categories: list[str] | None = None) -> None:
    """
    Register built-in tools with a registry.

    Args:
        registry: ToolRegistry to register with
        categories: List of categories to register ("filesystem", "shell", "git")
                   If None, registers all categories
    """
    all_categories = {
        "filesystem": FILESYSTEM_TOOLS,
        "shell": SHELL_TOOLS,
        "git": GIT_TOOLS,
    }

    if categories is None:
        categories = list(all_categories.keys())

    for category in categories:
        if category in all_categories:
            for tool in all_categories[category]:
                registry.register(tool)
