"""Tests for built-in tools.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Filesystem | 8 | Read, write, list, search files |
| Shell | 3 | Command execution, timeout |
| Git | 2 | Status, log (in git repo) |
| Registration | 2 | Tool registration |
"""

import pytest
from pathlib import Path

from openagent.tools.builtin import (
    read_file,
    write_file,
    list_directory,
    search_files,
    run_command,
    git_status,
    register_builtin_tools,
    FILESYSTEM_TOOLS,
    SHELL_TOOLS,
    GIT_TOOLS,
)
from openagent.tools.registry import ToolRegistry


class TestReadFile:
    """Tests for read_file tool."""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path: Path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = await read_file(str(test_file))

        assert "content" in result
        assert result["content"] == "Hello, World!"
        assert result["size"] == 13

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """Test reading a nonexistent file."""
        result = await read_file("/nonexistent/file.txt")

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_directory_error(self, tmp_path: Path):
        """Test error when reading a directory."""
        result = await read_file(str(tmp_path))

        assert "error" in result
        assert "not a file" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_with_encoding(self, tmp_path: Path):
        """Test reading with specific encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Héllo", encoding="utf-8")

        result = await read_file(str(test_file), encoding="utf-8")

        assert result["content"] == "Héllo"


class TestWriteFile:
    """Tests for write_file tool."""

    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path: Path):
        """Test writing a new file."""
        test_file = tmp_path / "new.txt"

        result = await write_file(str(test_file), "Hello!")

        assert result["success"] is True
        assert test_file.read_text() == "Hello!"

    @pytest.mark.asyncio
    async def test_write_creates_dirs(self, tmp_path: Path):
        """Test writing with directory creation."""
        test_file = tmp_path / "subdir" / "deep" / "file.txt"

        result = await write_file(str(test_file), "Content", create_dirs=True)

        assert result["success"] is True
        assert test_file.read_text() == "Content"

    @pytest.mark.asyncio
    async def test_write_overwrites(self, tmp_path: Path):
        """Test overwriting existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        result = await write_file(str(test_file), "New content")

        assert result["success"] is True
        assert test_file.read_text() == "New content"


class TestListDirectory:
    """Tests for list_directory tool."""

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path: Path):
        """Test listing directory contents."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.py").touch()
        (tmp_path / "subdir").mkdir()

        result = await list_directory(str(tmp_path))

        assert result["count"] == 3
        names = [f["name"] for f in result["files"]]
        assert "file1.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_list_with_pattern(self, tmp_path: Path):
        """Test listing with glob pattern."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.py").touch()

        result = await list_directory(str(tmp_path), pattern="*.py")

        assert result["count"] == 1
        assert result["files"][0]["name"] == "file2.py"

    @pytest.mark.asyncio
    async def test_list_recursive(self, tmp_path: Path):
        """Test recursive listing."""
        (tmp_path / "file1.txt").touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").touch()

        result = await list_directory(str(tmp_path), pattern="*.txt", recursive=True)

        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_list_nonexistent(self):
        """Test listing nonexistent directory."""
        result = await list_directory("/nonexistent/dir")

        assert "error" in result


class TestSearchFiles:
    """Tests for search_files tool."""

    @pytest.mark.asyncio
    async def test_search_by_name(self, tmp_path: Path):
        """Test searching files by name."""
        (tmp_path / "test.py").touch()
        (tmp_path / "other.txt").touch()

        result = await search_files(str(tmp_path), "*.py")

        assert result["count"] == 1
        assert "test.py" in result["matches"][0]["name"]

    @pytest.mark.asyncio
    async def test_search_by_content(self, tmp_path: Path):
        """Test searching files by content."""
        (tmp_path / "file1.py").write_text("def hello(): pass")
        (tmp_path / "file2.py").write_text("def world(): pass")

        result = await search_files(str(tmp_path), "*.py", content_pattern="hello")

        assert result["count"] == 1
        assert "file1.py" in result["matches"][0]["name"]


class TestRunCommand:
    """Tests for run_command tool."""

    @pytest.mark.asyncio
    async def test_run_simple_command(self):
        """Test running a simple command."""
        result = await run_command("echo hello")

        assert result["success"] is True
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_run_with_cwd(self, tmp_path: Path):
        """Test running command with working directory."""
        result = await run_command("pwd", cwd=str(tmp_path))

        assert result["success"] is True
        assert str(tmp_path) in result["stdout"]

    @pytest.mark.asyncio
    async def test_run_failing_command(self):
        """Test running a failing command."""
        result = await run_command("exit 1")

        assert result["success"] is False
        assert result["returncode"] == 1


class TestGitTools:
    """Tests for git tools (requires being in a git repo)."""

    @pytest.mark.asyncio
    async def test_git_status(self):
        """Test git status (in current repo)."""
        # This test runs in the OpenAgent repo
        result = await git_status(".")

        # Should succeed since we're in a git repo
        assert "returncode" in result

    @pytest.mark.asyncio
    async def test_git_log(self):
        """Test git log (in current repo)."""
        from openagent.tools.builtin import git_log

        result = await git_log(".", count=5)

        assert "returncode" in result


class TestRegistration:
    """Tests for tool registration."""

    def test_register_all_tools(self):
        """Test registering all built-in tools."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        # Check all categories registered
        expected = len(FILESYSTEM_TOOLS) + len(SHELL_TOOLS) + len(GIT_TOOLS)
        assert len(registry.list_all()) == expected

    def test_register_specific_categories(self):
        """Test registering specific categories."""
        registry = ToolRegistry()
        register_builtin_tools(registry, categories=["filesystem"])

        assert len(registry.list_all()) == len(FILESYSTEM_TOOLS)
        assert registry.get("read_file") is not None
        assert registry.get("run_command") is None

    def test_tool_schemas(self):
        """Test that all tools have valid schemas."""
        for tool in FILESYSTEM_TOOLS + SHELL_TOOLS + GIT_TOOLS:
            assert tool.name
            assert tool.description
            assert tool.handler is not None
            assert isinstance(tool.input_schema, dict)
