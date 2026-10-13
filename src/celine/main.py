"""Celine's terminal entry point: interactive loop and graceful shutdown."""

import sys

from celine.core import config
from celine.core.assistant import Assistant
from celine.llm import ollama_client
from celine.voice import Speaker


def main():
    assistant = Assistant(chat=ollama_client.chat)
    speaker = Speaker()
    listener = None
    print("Celine is ready. Type 'exit' or 'quit' to close. (Ctrl+C also works)")
    if config.MICROPHONE_ENABLED:
        commands = " or ".join(config.MICROPHONE_COMMANDS)
        print(f"Type {commands} to speak instead of typing.")
        if config.MICROPHONE_DIAGNOSTICS:
            print(
                f"Type {config.MICROPHONE_TEST_COMMAND} to test the microphone "
                f"or {config.MICROPHONE_DEVICES_COMMAND} to list input devices."
            )

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
            if user_text.lower() in config.MICROPHONE_COMMANDS:
                listener, user_text = _listen_once(listener)
                if not user_text:
                    continue
            elif user_text.lower() == config.MICROPHONE_TEST_COMMAND:
                listener = _diagnose_mic(listener)
                continue
            elif user_text.lower() == config.MICROPHONE_DEVICES_COMMAND:
                _list_mic_devices()
                continue

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
        if listener is not None:
            listener.shutdown()
        speaker.shutdown()


def _listen_once(listener):
    """Run one push-to-talk capture; return ``(listener, text or "")``."""
    from celine.voice.input import PushToTalk, run_push_to_talk

    if listener is None:
        listener = PushToTalk()
    text = run_push_to_talk(listener)
    return listener, text or ""


def _require_microphone():
    if not config.MICROPHONE_ENABLED:
        print("[mic] Microphone input is off. Set MICROPHONE_ENABLED = True.")
        return False
    return True


def _diagnose_mic(listener):
    """Run read-only diagnostics; never sends text to the assistant."""
    if not _require_microphone():
        return listener
    if not config.MICROPHONE_DIAGNOSTICS:
        print("[mic] Diagnostics are off. Set MICROPHONE_DIAGNOSTICS = True.")
        return listener
    from celine.voice.input import PushToTalk, run_mic_test

    if listener is None:
        listener = PushToTalk()
    run_mic_test(listener)
    return listener


def _list_mic_devices():
    if not _require_microphone():
        return
    from celine.voice.input import run_mic_devices

    run_mic_devices()


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
