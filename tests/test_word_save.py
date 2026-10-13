"""Safe Word save tests; no real filesystem or Word operations occur."""

from pathlib import Path

import pytest

from celine.core import prompts
from celine.core.assistant import Assistant
from celine.tools import registry
from celine.tools.word import folders
from celine.tools.word import tool as word_tool
from celine.tools.word.adapter import SAVE_FAILED, WordAdapterError


class FakeSaveAdapter:
    def __init__(self, error=None):
        self.error = error
        self.save_calls = []

    def save_document(self, trusted_path):
        self.save_calls.append(trusted_path)
        if self.error:
            raise self.error


class FakeChat:
    def __init__(self, *responses):
        self.responses = list(responses)

    def __call__(self, messages, tools):
        return self.responses.pop(0)


def tool_request(name, arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "function": {"name": name, "arguments": arguments}
        }],
    }


def install_safe_save_boundaries(
    monkeypatch,
    *,
    folder="documents",
    existence=(False, True),
    adapter_error=None,
):
    trusted_folder = Path(f"C:/Trusted/{folder.title()}")
    monkeypatch.setattr(
        word_tool,
        "_folder_resolver",
        lambda logical: (logical, trusted_folder),
    )
    states = iter(existence)
    exists_calls = []

    def path_exists(path):
        exists_calls.append(path)
        return next(states)

    monkeypatch.setattr(word_tool, "_path_exists", path_exists)
    adapter = FakeSaveAdapter(adapter_error)
    monkeypatch.setattr(word_tool, "_adapter_factory", lambda: adapter)
    return adapter, trusted_folder, exists_calls


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("Letter", "Letter.docx"),
        ("Letter.docx", "Letter.docx"),
        ("Letter.DOCX", "Letter.DOCX"),
        ("  Letter", "Letter.docx"),
    ],
)
def test_valid_filename_normalization(supplied, expected):
    assert word_tool._validated_docx_filename(supplied) == (expected, None)


@pytest.mark.parametrize(
    "filename",
    [
        "Letter.pdf",
        "",
        "x" * 116,
        "bad<name.docx",
        "bad>name.docx",
        'bad"name.docx',
        "bad:name.docx",
        "bad/name.docx",
        "bad\\name.docx",
        "bad|name.docx",
        "bad?name.docx",
        "bad*name.docx",
        ".",
        "..",
        "Letter.",
        "Letter.docx ",
        "CON.docx",
        "AUX.docx",
        "COM1.docx",
        "LPT9.docx",
        "bad\x01name.docx",
        "bad\x7fname.docx",
        "CON .docx",
        "Letter .docx",
    ],
)
def test_invalid_filenames_are_rejected(filename):
    safe_name, error = word_tool._validated_docx_filename(filename)
    assert safe_name is None
    assert "No save was attempted" in error


def test_final_filename_length_limit_is_120_characters():
    accepted = "x" * 115
    rejected = "x" * 116
    assert word_tool._validated_docx_filename(accepted)[0] == accepted + ".docx"
    assert word_tool._validated_docx_filename(rejected)[0] is None


@pytest.mark.parametrize("logical", ["documents", "desktop", "downloads"])
def test_known_folder_resolver_uses_fixed_guid(logical):
    seen = []
    expected_path = Path(f"C:/Redirected/{logical}")

    def resolver(folder_id):
        seen.append(folder_id)
        return expected_path

    resolved_name, resolved_path = folders.resolve_save_folder(
        logical,
        resolver=resolver,
    )
    assert resolved_name == logical
    assert resolved_path == expected_path
    assert seen == [folders._KNOWN_FOLDER_IDS[logical]]


@pytest.mark.parametrize(
    "folder",
    [
        r"C:\Users\Test\Documents",
        "D:\\",
        r"\\server\share",
        "../Desktop",
        "%USERPROFILE%",
        "file://documents",
        "pictures",
    ],
)
def test_folder_resolver_rejects_paths_and_unapproved_values(folder):
    with pytest.raises(ValueError):
        folders.resolve_save_folder(folder, resolver=lambda folder_id: None)


@pytest.mark.parametrize("folder", ["documents", "desktop", "downloads"])
def test_save_accepts_each_approved_folder(monkeypatch, folder):
    adapter, trusted_folder, exists_calls = install_safe_save_boundaries(
        monkeypatch,
        folder=folder,
    )
    result = word_tool.save_word_document("Letter", folder)
    expected_path = trusted_folder / "Letter.docx"
    assert adapter.save_calls == [str(expected_path)]
    assert exists_calls == [expected_path, expected_path]
    assert f"in {folder.title()}" in result


@pytest.mark.parametrize(
    ("filename", "folder"),
    [
        (r"C:\Windows\evil.docx", "documents"),
        (r"..\Desktop\evil.docx", "documents"),
        ("evil.docx", "D:\\"),
        ("evil.docx", "../downloads"),
    ],
)
def test_arbitrary_paths_never_reach_save_boundaries(
    monkeypatch, filename, folder
):
    resolver_calls = []
    adapter = FakeSaveAdapter()
    monkeypatch.setattr(
        word_tool,
        "_folder_resolver",
        lambda logical: resolver_calls.append(logical),
    )
    monkeypatch.setattr(word_tool, "_adapter_factory", lambda: adapter)
    result = word_tool.save_word_document(filename, folder)
    assert "No save was attempted" in result
    assert resolver_calls == []
    assert adapter.save_calls == []


def test_existing_file_refuses_without_save_or_automatic_rename(monkeypatch):
    adapter, trusted_folder, exists_calls = install_safe_save_boundaries(
        monkeypatch,
        existence=(True,),
    )
    result = word_tool.save_word_document("Letter.docx", "documents")
    assert "already exists" in result
    assert "No file was overwritten" in result
    assert "(1)" not in result
    assert adapter.save_calls == []
    assert exists_calls == [trusted_folder / "Letter.docx"]


def test_save_com_exception_is_unconfirmed(monkeypatch):
    error = WordAdapterError(
        "save_error",
        "internal",
        outcome=SAVE_FAILED,
    )
    adapter, _, _ = install_safe_save_boundaries(
        monkeypatch,
        existence=(False,),
        adapter_error=error,
    )
    result = word_tool.save_word_document("Letter.docx", "documents")
    assert result == "The Word save operation could not be confirmed."
    assert len(adapter.save_calls) == 1


def test_post_save_missing_file_is_unconfirmed(monkeypatch):
    adapter, _, _ = install_safe_save_boundaries(
        monkeypatch,
        existence=(False, False),
    )
    result = word_tool.save_word_document("Letter.docx", "documents")
    assert "completed" in result
    assert "could not be safely confirmed" in result
    assert len(adapter.save_calls) == 1


def test_post_save_file_exists_confirms_success(monkeypatch):
    adapter, _, _ = install_safe_save_boundaries(monkeypatch)
    result = word_tool.save_word_document("Letter.docx", "documents")
    assert result == (
        "Microsoft Word document saved successfully as 'Letter.docx' "
        "in Documents."
    )
    assert len(adapter.save_calls) == 1


def registry_call(arguments):
    return registry.run_tool_call({
        "function": {"name": "save_word_document", "arguments": arguments}
    })


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"folder": "documents"}, "missing required arguments: filename"),
        ({"filename": "Letter.docx"}, "missing required arguments: folder"),
        (
            {
                "filename": "Letter.docx",
                "folder": "documents",
                "path": "C:/unsafe",
            },
            "unexpected arguments: path",
        ),
        (
            {"filename": 123, "folder": "documents"},
            "'filename' must be a string",
        ),
        (
            {"filename": "Letter.docx", "folder": 123},
            "'folder' must be a string",
        ),
        (
            {"filename": "Letter.docx", "folder": "C:/unsafe"},
            "folder must be one of",
        ),
    ],
)
def test_registry_rejects_invalid_save_arguments(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda **kwargs: calls.append(kwargs),
    )
    _, result = registry_call(arguments)
    assert expected in result
    assert calls == []


def test_save_schema_is_exact():
    schema = next(
        item["function"]
        for item in registry.TOOL_SCHEMAS
        if item["function"]["name"] == "save_word_document"
    )
    parameters = schema["parameters"]
    assert set(parameters["properties"]) == {"filename", "folder"}
    assert parameters["properties"]["folder"]["enum"] == [
        "documents",
        "desktop",
        "downloads",
    ]
    assert parameters["required"] == ["filename", "folder"]
    assert parameters["additionalProperties"] is False


def test_prompt_preserves_save_scope_and_epistemic_rules():
    prompt = prompts.SYSTEM_PROMPT
    assert "documents, desktop, or downloads" in prompt
    assert "never overwrites or renames" in prompt
    assert "For a save-only request, call save_word_document directly" in prompt
    assert "cannot overwrite or delete files" in prompt
    assert "If a save is unconfirmed" in prompt


def test_write_then_save_orchestration(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: calls.append(("write", text, mode)) or "written",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda filename, folder: calls.append(("save", filename, folder))
        or "saved",
    )
    chat = FakeChat(
        tool_request("write_word_text", {"text": "Hello", "mode": "append"}),
        tool_request(
            "save_word_document",
            {"filename": "Hello.docx", "folder": "documents"},
        ),
        {"role": "assistant", "content": "Done."},
    )
    Assistant(chat=chat).ask("Write Hello and save it in Documents.")
    assert calls == [
        ("write", "Hello", "append"),
        ("save", "Hello.docx", "documents"),
    ]


def test_save_only_request_uses_save_tool_without_writing(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: calls.append(("write", text, mode)),
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda filename, folder: calls.append(("save", filename, folder))
        or "saved",
    )
    chat = FakeChat(
        tool_request(
            "save_word_document",
            {"filename": "Letter.docx", "folder": "documents"},
        ),
        {"role": "assistant", "content": "Saved."},
    )
    Assistant(chat=chat).ask("Save this as Letter.docx in Documents.")
    assert calls == [("save", "Letter.docx", "documents")]


def test_fresh_session_saves_already_open_document_without_creation(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda filename, folder: calls.append(("save", filename, folder))
        or "saved",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "create_word_document",
        lambda: calls.append(("create",)) or "created",
    )
    chat = FakeChat(
        tool_request(
            "save_word_document",
            {
                "filename": "Celine Formatting Test.docx",
                "folder": "documents",
            },
        ),
        {"role": "assistant", "content": "Saved."},
    )
    assistant = Assistant(chat=chat)
    assert len(assistant.history) == 1
    reply = assistant.ask(
        "Save this document as Celine Formatting Test.docx in Documents."
    )
    assert reply == "Saved."
    assert calls == [
        ("save", "Celine Formatting Test.docx", "documents")
    ]


def test_prompt_says_tools_determine_word_state_across_restart():
    prompt = prompts.SYSTEM_PROMPT
    assert "Registered tools, not conversational assumptions" in prompt
    assert "Restarting Celine starts a fresh chat but does not close Word" in prompt
    assert "does not need to have been created by Celine" in prompt
    assert "call save_word_document first" in prompt
    assert "instead of asking the user to confirm application state" in prompt


def test_open_create_write_save_orchestration(monkeypatch):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "open_application",
        lambda name: calls.append(("open", name)) or "opened",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "create_word_document",
        lambda: calls.append(("create",)) or "created",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "write_word_text",
        lambda text, mode: calls.append(("write", text, mode)) or "written",
    )
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "save_word_document",
        lambda filename, folder: calls.append(("save", filename, folder))
        or "saved",
    )
    chat = FakeChat(
        tool_request("open_application", {"name": "word"}),
        tool_request("create_word_document", {}),
        tool_request("write_word_text", {"text": "Hello", "mode": "append"}),
        tool_request(
            "save_word_document",
            {"filename": "Hello.docx", "folder": "documents"},
        ),
        {"role": "assistant", "content": "Done."},
    )
    Assistant(chat=chat).ask(
        "Open Word, write Hello, and save it as Hello.docx in Documents."
    )
    assert calls == [
        ("open", "word"),
        ("create",),
        ("write", "Hello", "append"),
        ("save", "Hello.docx", "documents"),
    ]


def test_save_tool_log_contains_metadata_only(monkeypatch, capsys):
    adapter, _, _ = install_safe_save_boundaries(monkeypatch)
    monkeypatch.setattr(word_tool.config, "TOOL_LOG", True)
    secret = "Private Letter.docx"
    word_tool.save_word_document(secret, "documents")
    output = capsys.readouterr().out
    assert len(adapter.save_calls) == 1
    assert "requested folder=documents filename_chars=19" in output
    assert "success folder=documents" in output
    assert secret not in output
