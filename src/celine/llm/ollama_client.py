"""The only module that talks to Ollama over HTTP (/api/chat)."""

import requests

from celine.core import config


class OllamaConnectionError(Exception):
    """Ollama is unreachable (server not running)."""


class OllamaHTTPError(Exception):
    """Ollama answered with an HTTP error status."""


class OllamaResponseError(Exception):
    """Ollama's answer could not be used (bad JSON or unexpected shape)."""


def chat(messages, tools):
    """Send one /api/chat request and return Ollama's message dict."""
    payload = {
        "model": config.MODEL,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    try:
        response = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError as exc:
        raise OllamaConnectionError(str(exc)) from exc
    except requests.exceptions.HTTPError as exc:
        raise OllamaHTTPError(str(exc)) from exc
    except requests.exceptions.RequestException as exc:
        raise OllamaResponseError(str(exc)) from exc
    except ValueError as exc:
        raise OllamaResponseError(str(exc)) from exc

    if not isinstance(data, dict):
        raise OllamaResponseError(f"Unexpected response from Ollama: {data!r}")

    message = data.get("message")
    if not isinstance(message, dict):
        raise OllamaResponseError(f"Unexpected response from Ollama: {data!r}")
    return message
