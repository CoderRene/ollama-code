# ollama_code

Terminal coding agent for a local [Ollama](https://ollama.com) model. You pick a server and a folder, then chat. The model can read, edit, search, and run commands inside that folder.

## Requirements

- Python 3
- Ollama running locally
- A model already pulled, for example `ollama pull gpt-oss:20b`

## Setup

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with `env\Scripts\activate`.

## Usage

```bash
python -m ollama_code
```

It asks for the Ollama server. Press Enter to use `OLLAMA_HOST`, or `http://127.0.0.1:11434` when that variable is unset. Then pick a workspace folder. Every path the model uses stays inside that folder.

```bash
python -m ollama_code --model llama3.2 --temperature 0.2
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--model` | `gpt-oss:20b` | Ollama model name |
| `--system` | none | Extra system prompt |
| `--max-new-tokens` | `1024` | Tokens generated per reply |
| `--temperature` | `0` | Sampling temperature. `0` is greedy |
| `--num-ctx` | `4096` | Context window sent to Ollama |

### Commands

- `/help` shows commands and the current session
- `/clear` drops the conversation
- `/exit` and `/quit` leave

Enter sends the message. Shift+Enter inserts a newline. Use Alt+Enter when the terminal does not send Shift+Enter.

### Tools

The model can call these tools, limited to the selected folder:

- `bash` runs a shell command
- `read` reads a file
- `write` creates or overwrites a file
- `edit` replaces one exact string in a file
- `grep` searches file contents
- `glob` finds files by name

## Build

On macOS:

```bash
./build_mac.sh
```

The script installs dependencies and PyInstaller, then writes `dist/ollama_code`.

On Windows:

```powershell
.\build_windows.ps1
```

The script installs dependencies and PyInstaller, then writes `dist\ollama_code.exe`.

## License

MIT. See [LICENSE](LICENSE).
