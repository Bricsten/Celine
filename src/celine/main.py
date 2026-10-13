"""Celine's terminal entry point: interactive loop and graceful shutdown."""

import sys

from celine.core import config
from celine.core.assistant import Assistant
from celine.llm import ollama_client
from celine.voice import Speaker


def main():
    assistant = Assistant(chat=ollama_client.chat)
    speaker = Speaker()
    print("Celine is ready. Type 'exit' or 'quit' to close. (Ctrl+C also works)")

    try:
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
            except ollama_client.OllamaTimeoutError as exc:
                if exc.tool_results:
                    name, result = exc.tool_results[-1]
                    print(
                        "Celine: Ollama timed out after a tool result was "
                        f"recorded. {name}: {result} No automatic retry was "
                        "performed."
                    )
                else:
                    print(
                        "Celine: Ollama timed out before any tool was selected. "
                        "No tool operation was performed."
                    )
            except ollama_client.OllamaResponseError as exc:
                print(f"Celine: Something went wrong ({exc}).")
            else:
                print(f"Celine: {reply}")
                _speak_reply(speaker, reply)
    finally:
        speaker.shutdown()


def _speak_reply(speaker, reply):
    """Speak the final reply, reporting honestly if playback did not happen."""
    result = speaker.speak(reply)
    if (
        speaker.requested
        and not result.spoken
        and result.reason not in (None, "empty_text")
    ):
        print(f"[voice] speech was not played ({result.reason}).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGoodbye.")
        sys.exit(0)
