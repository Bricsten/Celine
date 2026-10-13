"""Mock-only tests for fixed, range-scoped Word block formatting."""

import pytest

from celine.core import prompts
from celine.tools import registry
from celine.tools.word import tool as word_tool
from celine.tools.word.adapter import (
    ATTACHMENT_FAILED,
    BLOCK_FORMAT_FAILED,
    BLOCK_INSERT_FAILED,
    WORD_ALIGNMENT_VALUES,
    WORD_FONT_NAME,
    WORD_STYLE_PRESETS,
    ComWordAdapter,
    WordAdapterError,
)


class FakeComError(Exception):
    pass


class Collection:
    def __init__(self, items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


class Window:
    Hwnd = 101


class NativeWindow:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def is_enabled(self):
        return self.enabled


class Runtime:
    def __init__(self):
        self.initialized = 0
        self.uninitialized = 0

    def CoInitialize(self):
        self.initialized += 1

    def CoUninitialize(self):
        self.uninitialized += 1


class MetadataRange:
    def __init__(self, start, end):
        self.Start = start
        self.End = end


class Paragraph:
    def __init__(self, start, end):
        self.Range = MetadataRange(start, end)


class FormatProperties:
    def __init__(self, document, range_key, category):
        object.__setattr__(self, "document", document)
        object.__setattr__(self, "range_key", range_key)
        object.__setattr__(self, "category", category)

    def __setattr__(self, name, value):
        document = object.__getattribute__(self, "document")
        if document.format_error is not None:
            error = document.format_error
            document.format_error = None
            raise error
        document.formatting.append((
            object.__getattribute__(self, "range_key"),
            object.__getattribute__(self, "category"),
            name,
            value,
        ))


class EditableRange:
    def __init__(self, document, start, end):
        self.document = document
        self.Start = start
        self.End = end
        key = (start, end)
        self.Font = FormatProperties(document, key, "font")
        self.ParagraphFormat = FormatProperties(document, key, "paragraph")

    def InsertAfter(self, payload):
        self.document.insertions.append((self.Start, self.End, payload))
        if self.document.insert_error is not None:
            raise self.document.insert_error
        self.document.Content.End += len(payload)


class Document:
    def __init__(
        self,
        *,
        content_end=1,
        paragraphs=((0, 1),),
        read_only=False,
        protection_type=-1,
        window_count=1,
        window_hwnd=101,
        insert_error=None,
        format_error=None,
    ):
        self.Content = MetadataRange(0, content_end)
        self.Paragraphs = Collection([
            Paragraph(start, end) for start, end in paragraphs
        ])
        self.ReadOnly = read_only
        self.ProtectionType = protection_type
        self.Windows = Collection([
            type("DocumentWindow", (), {"Hwnd": window_hwnd})()
            for _ in range(window_count)
        ])
        self.insert_error = insert_error
        self.format_error = format_error
        self.insertions = []
        self.range_requests = []
        self.formatting = []

    def Range(self, start, end):
        self.range_requests.append((start, end))
        return EditableRange(self, start, end)


class Application:
    def __init__(
        self,
        document,
        *,
        documents=None,
        window_count=1,
        window_hwnd=101,
        protected_view_count=0,
    ):
        documents = [document] if documents is None else documents
        self.Documents = Collection(documents)
        self.Windows = Collection([
            type("ApplicationWindow", (), {"Hwnd": window_hwnd})()
            for _ in range(window_count)
        ])
        self.ProtectedViewWindows = Collection(
            [object()] * protected_view_count
        )


def make_adapter(
    document=None,
    *,
    application=None,
    handles=(101,),
    enabled=True,
    get_active_error=None,
):
    document = document or Document()
    application = application or Application(document)
    runtime = Runtime()

    def get_active_object(progid):
        if get_active_error is not None:
            raise get_active_error
        return application

    adapter = ComWordAdapter(
        find_handles=lambda: list(handles),
        wrap_window=lambda hwnd: NativeWindow(enabled),
        get_active_object=get_active_object,
        com_runtime=runtime,
        com_error_type=FakeComError,
        clock=lambda: 0,
        sleep=lambda seconds: None,
        readiness_timeout=0,
    )
    return adapter, document, runtime


@pytest.mark.parametrize("style", WORD_STYLE_PRESETS)
def test_each_approved_style_uses_fixed_preset(style):
    adapter, document, _ = make_adapter()
    adapter.add_block("Block", style, "left")
    block_values = {
        (category, name): value
        for target, category, name, value in document.formatting
        if target == (0, 5)
    }
    size, bold = WORD_STYLE_PRESETS[style]
    assert block_values == {
        ("font", "Name"): WORD_FONT_NAME,
        ("font", "Size"): size,
        ("font", "Bold"): bold,
        ("paragraph", "Alignment"): 0,
    }


@pytest.mark.parametrize("alignment", WORD_ALIGNMENT_VALUES)
def test_each_approved_alignment_uses_fixed_constant(alignment):
    adapter, document, _ = make_adapter()
    adapter.add_block("Block", "normal", alignment)
    assert (
        (0, 5),
        "paragraph",
        "Alignment",
        WORD_ALIGNMENT_VALUES[alignment],
    ) in document.formatting


def test_empty_document_uses_terminal_paragraph_without_leading_blank():
    adapter, document, _ = make_adapter()
    adapter.add_block("Title", "title", "center")
    assert document.insertions == [(0, 0, "Title\r")]
    assert document.range_requests == [(0, 0), (0, 5), (6, 7)]


def test_existing_content_gets_exactly_one_boundary_before_block():
    document = Document(content_end=12, paragraphs=((0, 6), (6, 12)))
    adapter, _, _ = make_adapter(document)
    adapter.add_block("Next", "heading_1", "left")
    assert document.insertions == [(11, 11, "\rNext\r")]
    assert (12, 16) in document.range_requests
    assert (17, 18) in document.range_requests


def test_existing_terminal_empty_paragraph_is_consumed_without_extra_blank():
    document = Document(
        content_end=13,
        paragraphs=((0, 6), (6, 12), (12, 13)),
    )
    adapter, _, _ = make_adapter(document)
    adapter.add_block("Next", "heading_2", "right")
    assert document.insertions == [(12, 12, "Next\r")]
    assert document.range_requests == [(12, 12), (12, 16), (17, 18)]


def test_only_new_block_and_trailing_paragraph_are_formatted():
    document = Document(content_end=6, paragraphs=((0, 6),))
    adapter, _, _ = make_adapter(document)
    adapter.add_block("New", "heading_1", "center")
    formatted_ranges = {entry[0] for entry in document.formatting}
    assert formatted_ranges == {(6, 9), (10, 11)}
    assert all(start >= 6 for start, _ in formatted_ranges)


def test_trailing_paragraph_is_reset_to_normal_left_for_later_text():
    adapter, document, _ = make_adapter()
    adapter.add_block("Heading", "heading_1", "center")
    trailing_values = {
        (category, name): value
        for target, category, name, value in document.formatting
        if target == (8, 9)
    }
    assert trailing_values == {
        ("font", "Name"): WORD_FONT_NAME,
        ("font", "Size"): 12,
        ("font", "Bold"): 0,
        ("paragraph", "Alignment"): 0,
    }


@pytest.mark.parametrize(
    "application",
    [
        Application(Document(), documents=[Document(), Document()]),
        Application(Document(), window_count=2),
        Application(Document(read_only=True)),
        Application(Document(protection_type=0)),
        Application(Document(), protected_view_count=1),
    ],
)
def test_unsafe_document_states_are_rejected_before_insertion(application):
    document = application.Documents.Item(1)
    adapter, _, _ = make_adapter(document, application=application)
    with pytest.raises(WordAdapterError):
        adapter.add_block("Unsafe", "normal", "left")
    assert document.insertions == []


def test_multiple_native_windows_are_rejected_before_attachment():
    adapter, document, _ = make_adapter(handles=(101, 202))
    with pytest.raises(WordAdapterError) as caught:
        adapter.add_block("Unsafe", "normal", "left")
    assert caught.value.reason == "ambiguous_word_target"
    assert document.insertions == []


def test_com_failure_before_insertion_is_attachment_failure():
    adapter, document, runtime = make_adapter(
        get_active_error=FakeComError("busy")
    )
    with pytest.raises(WordAdapterError) as caught:
        adapter.add_block("Block", "normal", "left")
    assert caught.value.outcome == ATTACHMENT_FAILED
    assert document.insertions == []
    assert runtime.initialized == runtime.uninitialized == 1


def test_insertion_failure_is_unconfirmed_and_never_retried():
    document = Document(insert_error=FakeComError("unknown outcome"))
    adapter, _, _ = make_adapter(document)
    with pytest.raises(WordAdapterError) as caught:
        adapter.add_block("Once", "normal", "left")
    assert caught.value.outcome == BLOCK_INSERT_FAILED
    assert document.insertions == [(0, 0, "Once\r")]
    assert document.formatting == []


def test_format_failure_reports_inserted_text_and_never_duplicates_it():
    document = Document(format_error=FakeComError("format failed"))
    adapter, _, _ = make_adapter(document)
    with pytest.raises(WordAdapterError) as caught:
        adapter.add_block("Once", "heading_1", "center")
    assert caught.value.outcome == BLOCK_FORMAT_FAILED
    assert document.insertions == [(0, 0, "Once\r")]
    assert "text was inserted" in caught.value.user_message.lower()


class PublicFakeAdapter:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def add_block(self, text, style, alignment):
        self.calls.append((text, style, alignment))
        if self.error:
            raise self.error


def install_public_adapter(monkeypatch, error=None):
    adapter = PublicFakeAdapter(error)
    monkeypatch.setattr(word_tool, "_adapter_factory", lambda: adapter)
    return adapter


@pytest.mark.parametrize(
    ("text", "style", "alignment", "expected"),
    [
        ("", "normal", "left", "Text is empty"),
        (None, "normal", "left", "Text must be a string"),
        ("x", "unknown", "left", "style is not allowed"),
        ("x", "normal", "middle", "alignment is not allowed"),
    ],
)
def test_public_validation_rejects_before_adapter(
    monkeypatch, text, style, alignment, expected
):
    adapter = install_public_adapter(monkeypatch)
    assert expected in word_tool.add_word_block(text, style, alignment)
    assert adapter.calls == []


def test_public_text_limit(monkeypatch):
    adapter = install_public_adapter(monkeypatch)
    text = "x" * word_tool.MAX_WORD_TEXT_LENGTH
    assert "successfully" in word_tool.add_word_block(
        text, "normal", "justify"
    )
    assert adapter.calls == [(text, "normal", "justify")]
    assert "10,000-character limit" in word_tool.add_word_block(
        text + "x", "normal", "justify"
    )
    assert len(adapter.calls) == 1


def test_public_partial_format_failure_is_epistemically_accurate(monkeypatch):
    error = WordAdapterError(
        "block_format_error",
        "internal",
        outcome=BLOCK_FORMAT_FAILED,
    )
    install_public_adapter(monkeypatch, error)
    result = word_tool.add_word_block("Text", "heading_1", "center")
    assert result == (
        "The text was inserted in Microsoft Word, but its formatting could "
        "not be confirmed."
    )


def registry_call(arguments):
    return registry.run_tool_call({
        "function": {"name": "add_word_block", "arguments": arguments}
    })


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"style": "normal", "alignment": "left"}, "missing required"),
        ({"text": "x", "alignment": "left"}, "missing required"),
        ({"text": "x", "style": "normal"}, "missing required"),
        (
            {"text": "x", "style": "normal", "alignment": "left", "size": 99},
            "unexpected arguments: size",
        ),
        (
            {"text": 1, "style": "normal", "alignment": "left"},
            "must be a string",
        ),
        (
            {"text": "x", "style": "custom", "alignment": "left"},
            "style must be one of",
        ),
        (
            {"text": "x", "style": "normal", "alignment": "middle"},
            "alignment must be one of",
        ),
    ],
)
def test_registry_rejects_invalid_arguments(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "add_word_block",
        lambda **kwargs: calls.append(kwargs),
    )
    _, result = registry_call(arguments)
    assert expected in result
    assert calls == []


def test_schema_is_exact():
    schema = next(
        entry["function"]
        for entry in registry.TOOL_SCHEMAS
        if entry["function"]["name"] == "add_word_block"
    )
    parameters = schema["parameters"]
    assert set(parameters["properties"]) == {"text", "style", "alignment"}
    assert parameters["properties"]["style"]["enum"] == [
        "normal", "heading_1", "heading_2", "title"
    ]
    assert parameters["properties"]["alignment"]["enum"] == [
        "left", "center", "right", "justify"
    ]
    assert parameters["required"] == ["text", "style", "alignment"]
    assert parameters["additionalProperties"] is False


def test_prompt_preserves_formatting_scope_and_epistemic_boundary():
    prompt = prompts.SYSTEM_PROMPT
    lower_prompt = prompt.lower()
    assert "add_word_block" in prompt
    assert "only to the newly inserted block" in lower_prompt
    assert "cannot reformat existing word text" in lower_prompt
    assert "saving remains a separate operation" in lower_prompt
    assert "complete document contents" in lower_prompt
