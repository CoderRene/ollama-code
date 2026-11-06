import glob
import shutil
import subprocess
from pathlib import Path

TOOL_RESULT_LIMIT = 6000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the workspace and return stdout, stderr, and the exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run."},
                    "timeout": {"type": "integer", "description": "Seconds before the command is killed. Default 120."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a text file. Lines are numbered. Use offset and limit for long files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "description": "First line to read, starting at 1."},
                    "limit": {"type": "integer", "description": "How many lines to read. Default 200."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create or overwrite a file with the given contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "contents": {"type": "string"},
                },
                "required": ["path", "contents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace one exact occurrence of old_string with new_string in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents for a regular expression and return matching lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "description": "File or directory to search. Defaults to the workspace."},
                    "glob": {"type": "string", "description": "Optional filename filter, such as *.py."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files by a glob pattern, such as **/*.py.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "description": "Directory to search. Defaults to the workspace."},
                },
                "required": ["pattern"],
            },
        },
    },
]


def tool_system_prompt(workspace):
    return (
        "You are a coding agent working only in "
        f"{workspace}. Use bash, read, write, edit, grep, and glob to inspect and change "
        "files instead of guessing. Every path must stay inside that folder. "
        "After the tools finish, answer the user in plain text."
    )


def run_tool(workspace, name, arguments):
    workspace = Path(workspace)
    arguments = arguments or {}
    if name == "bash":
        return _bash(workspace, arguments.get("command", ""), arguments.get("timeout", 120))
    if name == "read":
        return _read(workspace, arguments.get("path", ""), arguments.get("offset", 1), arguments.get("limit", 200))
    if name == "write":
        return _write(workspace, arguments.get("path", ""), arguments.get("contents", ""))
    if name == "edit":
        return _edit(
            workspace,
            arguments.get("path", ""),
            arguments.get("old_string", ""),
            arguments.get("new_string", ""),
        )
    if name == "grep":
        return _grep(workspace, arguments.get("pattern", ""), arguments.get("path") or ".", arguments.get("glob"))
    if name == "glob":
        return _glob(workspace, arguments.get("pattern", ""), arguments.get("path") or ".")
    return f"Unknown tool: {name}"


def _clip(text):
    if len(text) <= TOOL_RESULT_LIMIT:
        return text
    omitted = len(text) - TOOL_RESULT_LIMIT
    return text[:TOOL_RESULT_LIMIT] + f"\n... truncated, {omitted} characters omitted"


def _resolve(workspace, path):
    root = workspace.resolve()
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raw = root / raw
    resolved = raw.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _inside(workspace, path):
    if not path:
        return None, "No path was provided."
    resolved = _resolve(workspace, path)
    if resolved is None:
        return None, "That path is outside the selected folder."
    return resolved, None


def _bash(workspace, command, timeout):
    command = str(command).strip()
    if not command:
        return "No command was provided."
    try:
        seconds = min(max(int(timeout), 1), 300)
    except (TypeError, ValueError):
        seconds = 120
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return _clip(f"Timed out after {seconds}s\n{output}")
    output = completed.stdout
    if completed.stderr:
        output += ("\n" if output else "") + completed.stderr
    return _clip(f"exit {completed.returncode}\n{output}")


def _read(workspace, path, offset, limit):
    file, error = _inside(workspace, path)
    if error:
        return error
    if not file.is_file():
        return f"Not a file: {file}"
    lines = file.read_text(errors="replace").splitlines()
    try:
        start = max(int(offset), 1)
        count = max(int(limit), 1)
    except (TypeError, ValueError):
        start, count = 1, 200
    chosen = lines[start - 1 : start - 1 + count]
    numbered = "\n".join(f"{start + index}|{line}" for index, line in enumerate(chosen))
    return _clip(f"{file} ({len(lines)} lines)\n{numbered}")


def _write(workspace, path, contents):
    file, error = _inside(workspace, path)
    if error:
        return error
    file.parent.mkdir(parents=True, exist_ok=True)
    text = "" if contents is None else str(contents)
    file.write_text(text)
    return f"Wrote {file} ({len(text)} characters)"


def _edit(workspace, path, old_string, new_string):
    if not path:
        return "No path was provided."
    if old_string is None or old_string == "":
        return "old_string is empty."
    file, error = _inside(workspace, path)
    if error:
        return error
    if not file.is_file():
        return f"Not a file: {file}"
    text = file.read_text(errors="replace")
    found = text.count(str(old_string))
    if found == 0:
        return "old_string was not found in the file."
    if found > 1:
        return f"old_string matched {found} times. Include more surrounding text so it is unique."
    file.write_text(text.replace(str(old_string), "" if new_string is None else str(new_string), 1))
    return f"Edited {file}"


def _grep(workspace, pattern, path, file_glob):
    if not pattern:
        return "No pattern was provided."
    root, error = _inside(workspace, path)
    if error:
        return error
    if not root.exists():
        return f"Path does not exist: {root}"
    rg = shutil.which("rg")
    if rg:
        command = [rg, "-n", "--heading", "--max-count", "40", "--glob", "!.git/**", "--glob", "!env/**"]
        if file_glob:
            command.extend(["--glob", file_glob])
        command.extend([pattern, str(root)])
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode == 1:
            return "No matches."
        if completed.returncode not in (0, 1):
            return _clip(completed.stderr or f"rg exited {completed.returncode}")
        return _clip(completed.stdout or "No matches.")

    matches = []
    files = [root] if root.is_file() else list(root.rglob("*"))
    for file in files:
        if not file.is_file() or "env" in file.parts or ".git" in file.parts:
            continue
        if file_glob and not file.match(file_glob):
            continue
        try:
            lines = file.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if pattern in line:
                matches.append(f"{file}:{number}:{line}")
                if len(matches) >= 40:
                    return _clip("\n".join(matches))
    return _clip("\n".join(matches) if matches else "No matches.")


def _glob(workspace, pattern, path):
    if not pattern:
        return "No pattern was provided."
    root, error = _inside(workspace, path)
    if error:
        return error
    if not root.is_dir():
        return f"Not a directory: {root}"
    matches = []
    for match in glob.glob(str(root / pattern), recursive=True):
        file = Path(match)
        if "env" in file.parts or ".git" in file.parts:
            continue
        matches.append(str(file))
        if len(matches) >= 200:
            break
    matches.sort()
    return _clip("\n".join(matches) if matches else "No matches.")
