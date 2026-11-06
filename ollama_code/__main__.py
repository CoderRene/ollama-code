import argparse

DEFAULT_MODEL = "gpt-oss:20b"


def parse_args():
    parser = argparse.ArgumentParser(
        prog="ollama_code",
        description="Work with a local Ollama model in the terminal.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--system", default=None, help="System prompt for the conversation")
    parser.add_argument("--max-new-tokens", type=int, default=1024, help="Max tokens to generate per reply")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature. 0 is greedy",
    )
    parser.add_argument("--num-ctx", type=int, default=4096, help="Context window sent to Ollama")
    return parser.parse_args()


def main():
    import multiprocessing

    multiprocessing.freeze_support()
    args = parse_args()
    from ollama_code.repl import run

    run(args)


if __name__ == "__main__":
    main()
