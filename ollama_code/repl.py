import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import vt100_parser
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from rich.console import Console

from ollama_code.tools import TOOLS, run_tool, tool_system_prompt

PROMPT_STYLE = Style.from_dict({"prompt": "bold"})


def run(args):
    console = Console(highlight=False)
    host = _ask_server(console)
    workspace = _ask_folder(console)
    console.print(f"\n[bold]ollama_code[/bold]  {args.model}")
    console.print(f"[dim]{host}[/dim]")
    console.print(f"[dim]{workspace}[/dim]")
    console.print(
        "[dim]Tools: bash, read, write, edit, grep, glob. "
        "Enter to send, Shift+Enter for a newline. /help for commands.[/dim]\n"
    )

    try:
        models = _installed_models(host)
    except urllib.error.URLError as exc:
        console.print(f"[red]Could not reach Ollama at {host}:[/red] {exc.reason}")
        console.print("[dim]Start it with `brew services start ollama` or `ollama serve`.[/dim]")
        raise SystemExit(1) from exc

    if not _model_installed(models, args.model):
        names = ", ".join(models) if models else "(none)"
        console.print(f"[red]{args.model} is not installed.[/red] Installed models: {names}")
        console.print(f"[dim]Pull it with `ollama pull {args.model}`.[/dim]")
        raise SystemExit(1)

    console.print("[green]Ready.[/green]\n")

    messages = [{"role": "system", "content": tool_system_prompt(workspace)}]
    if args.system:
        messages.append({"role": "system", "content": args.system})
    system_messages = list(messages)

    # prompt_toolkit treats these Shift+Enter sequences as Enter. Point them at
    # Ctrl-J so Enter can submit and Shift+Enter can insert a newline.
    ANSI_SEQUENCES["\x1b[27;2;13~"] = Keys.ControlJ
    ANSI_SEQUENCES["\x1b[13;2u"] = Keys.ControlJ
    vt100_parser._IS_PREFIX_OF_LONGER_MATCH_CACHE.clear()

    bindings = KeyBindings()

    @bindings.add("enter", eager=True)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @bindings.add("c-j", eager=True)
    def _newline(event):
        event.current_buffer.insert_text("\n")

    @bindings.add("escape", "enter", eager=True)
    def _newline_alt(event):
        event.current_buffer.insert_text("\n")

    session = PromptSession(history=InMemoryHistory(), key_bindings=bindings, style=PROMPT_STYLE)

    while True:
        try:
            text = session.prompt([("class:prompt", "> ")], multiline=True)
        except EOFError:
            console.print("\n[dim]Bye.[/dim]")
            break
        except KeyboardInterrupt:
            console.print()
            continue

        command = text.strip()
        if not command:
            continue
        if command in {"/exit", "/quit"}:
            console.print("[dim]Bye.[/dim]")
            break
        if command == "/help":
            console.print(
                "\n".join(
                    [
                        "[bold]Commands[/bold]",
                        "  /help            show this help",
                        "  /clear           drop the conversation",
                        "  /exit, /quit     leave",
                        "",
                        "[bold]Input[/bold]",
                        "  Enter            send",
                        "  Shift+Enter      newline (Alt+Enter if the terminal does not send Shift+Enter)",
                        "",
                        "[bold]Tools[/bold]",
                        "  bash             run a shell command",
                        "  read             read a file",
                        "  write            create or overwrite a file",
                        "  edit             replace one exact string in a file",
                        "  grep             search file contents",
                        "  glob             find files by name",
                        "",
                        "[bold]This session[/bold]",
                        f"  model            {args.model}",
                        f"  server           {host}",
                        f"  folder           {workspace}",
                        f"  system           {args.system or '(none)'}",
                        f"  max-new-tokens   {args.max_new_tokens}",
                        f"  temperature      {args.temperature}",
                        f"  num-ctx          {args.num_ctx}",
                    ]
                )
            )
            console.print()
            continue
        if command == "/clear":
            messages = list(system_messages)
            console.print("[dim]Conversation cleared.[/dim]\n")
            continue

        messages.append({"role": "user", "content": command})
        try:
            _run_turn(console, host, messages, args, workspace)
        except Exception:
            messages.pop()


def _ask_server(console):
    default = _host_url(os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434")
    console.print("[bold]Ollama server[/bold]")
    console.print(f"[dim]Press Enter for {default}, or type another URL.[/dim]")
    try:
        typed = PromptSession().prompt("server> ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(1) from None
    return _host_url(typed or default)


def _ask_folder(console):
    current = Path.cwd().resolve()
    session = PromptSession()
    while True:
        directories = sorted(
            path for path in current.iterdir() if path.is_dir() and not path.name.startswith(".")
        )
        console.print(f"\n[bold]Folder[/bold]  {current}")
        console.print("  [cyan].[/cyan]   use this folder")
        if current.parent != current:
            console.print("  [cyan]..[/cyan]  up one level")
        for index, path in enumerate(directories, start=1):
            console.print(f"  [cyan]{index}[/cyan]   {path.name}")
        console.print("[dim]Number to open, . to use this folder, .. to go up, or type a path.[/dim]")
        try:
            choice = session.prompt("folder> ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(1) from None
        if choice in {"", "."}:
            return current
        if choice == "..":
            current = current.parent
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(directories):
            current = directories[int(choice) - 1]
            continue
        candidate = Path(choice).expanduser()
        if not candidate.is_absolute():
            candidate = current / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            console.print(f"[red]Not a folder:[/red] {choice}")
            continue
        if candidate.is_dir():
            current = candidate
            continue
        console.print(f"[red]Not a folder:[/red] {choice}")


def _host_url(host):
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    parsed = urlparse(host)
    hostname = parsed.hostname or "127.0.0.1"
    if hostname in {"0.0.0.0", "::"}:
        hostname = "127.0.0.1"
    local = hostname in {"127.0.0.1", "localhost"}
    port = parsed.port
    if port is None and local:
        port = 11434
    if port is None:
        return f"{parsed.scheme}://{hostname}"
    return f"{parsed.scheme}://{hostname}:{port}"


def _installed_models(host):
    with urllib.request.urlopen(host + "/api/tags", timeout=5) as response:
        payload = json.load(response)
    return [model["name"] for model in payload.get("models", [])]


def _model_installed(models, name):
    for installed in models:
        if installed == name:
            return True
        if ":" not in name and installed.split(":")[0] == name:
            return True
    return False


def _run_turn(console, host, messages, args, workspace):
    console.print("[bold]Assistant[/bold]")
    started = len(messages)
    used_tools = False
    showed_status = False

    def show_thinking():
        nonlocal showed_status
        if not showed_status:
            console.print("[dim]Thinking...[/dim]")
            showed_status = True

    try:
        for _ in range(8):
            content, tool_calls = _chat_once(console, host, messages, args, show_thinking)
            if not tool_calls:
                if content.strip():
                    messages.append({"role": "assistant", "content": content})
                elif not used_tools:
                    console.print("[dim](empty reply)[/dim]", end="")
                console.print("\n")
                return
            for call in tool_calls:
                name, arguments = _tool_call_parts(call)
                call.setdefault("function", {})["name"] = name
                call["function"]["arguments"] = arguments
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            show_thinking()
            for call in tool_calls:
                name = call["function"]["name"]
                arguments = call["function"]["arguments"]
                try:
                    result = run_tool(workspace, name, arguments)
                except Exception as exc:
                    result = f"Tool failed: {exc}"
                messages.append({"role": "tool", "tool_name": name, "content": result})
            used_tools = True
        console.print("[dim]Stopped after 8 tool rounds.[/dim]\n")
    except KeyboardInterrupt:
        if len(messages) == started:
            messages.pop()
        console.print("\n[dim]Stopped.[/dim]\n")
    except Exception as exc:
        console.print(f"\n[red]Generation failed:[/red] {exc}\n")
        if len(messages) == started:
            raise


def _chat_once(console, host, messages, args, show_thinking):
    payload = {
        "model": args.model,
        "messages": messages,
        "tools": TOOLS,
        "stream": True,
        "options": {
            "temperature": args.temperature,
            "num_predict": args.max_new_tokens,
            "num_ctx": args.num_ctx,
        },
    }
    request = urllib.request.Request(
        host + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    content = ""
    tool_calls = []
    try:
        with urllib.request.urlopen(request) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                chunk = json.loads(raw_line)
                if chunk.get("error"):
                    raise RuntimeError(chunk["error"])
                message = chunk.get("message") or {}
                if message.get("thinking"):
                    show_thinking()
                piece = message.get("content") or ""
                if piece:
                    console.print(piece, end="")
                    console.file.flush()
                    content += piece
                for call in message.get("tool_calls") or []:
                    _absorb_tool_call(tool_calls, call)
                if chunk.get("done"):
                    break
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(detail) from exc
    return content, tool_calls


def _absorb_tool_call(tool_calls, call):
    function = call.get("function") or {}
    name = function.get("name") or ""
    arguments = function.get("arguments")
    if not name and tool_calls and isinstance(arguments, str):
        previous = tool_calls[-1]["function"]
        current = previous.get("arguments")
        if isinstance(current, str):
            previous["arguments"] = current + arguments
        elif not current:
            previous["arguments"] = arguments
        return
    tool_calls.append({"function": {"name": name, "arguments": {} if arguments is None else arguments}})


def _tool_call_parts(call):
    function = call.get("function") or {}
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {"_raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}
    return function.get("name") or "unknown", arguments
