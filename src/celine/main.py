"""Celine's terminal entry point: interactive loop and graceful shutdown."""

import sys

from celine.core import config
from celine.core.assistant import Assistant
from celine.llm import ollama_client


def main():
    assistant = Assistant(chat=ollama_client.chat)
    print("Celine is ready. Type 'exit' or 'quit' to close. (Ctrl+C also works)")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit"):
            print("Goodbye.")
            break

        try:
            reply = assistant.ask(user_text)
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break
        except ollama_client.OllamaConnectionError:
            print(
                "Celine: I can't reach Ollama. "
                f"Is it running on {config.OLLAMA_BASE_URL} ?"
            )
        except ollama_client.OllamaHTTPError as exc:
            print(f"Celine: Ollama returned an error ({exc}).")
        except ollama_client.OllamaResponseError as exc:
            print(f"Celine: Something went wrong ({exc}).")
        else:
            print(f"Celine: {reply}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGoodbye.")
        sys.exit(0)
