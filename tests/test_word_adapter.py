"""Unit tests for the Word COM adapter. Word is never launched."""

import pytest

from celine.tools.word.adapter import (
    ATTACHMENT_FAILED,
    CREATION_ACTIVATION_FAILED,
    CREATION_FAILED,
    CREATION_UNCONFIRMED,
    WRITE_FAILED,
    ComWordAdapter,
    WordAdapterError,
)


class FakeComError(Exception):
    pass


class FakeRuntime:
    def __init__(self):
        self.initialized = 0
        self.uninitialized = 0

    def CoInitialize(self):
        self.initialized += 1

    def CoUninitialize(self):
        self.uninitialized += 1


class FakeCollection:
    def __init__(self, items=()):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


class FakeDocuments(FakeCollection):
    def __init__(
        self,
        application,
        document,
        *,
        add_error=None,
        post_documents=None,
        post_window_count=1,
        post_window_hwnd=101,
        expose_post_window_hwnd=True,
    ):
        super().__init__(())
        self.application = application
        self.document = document
        self.add_error = add_error
        self.post_documents = post_documents
        self.post_window_count = post_window_count
        self.post_window_hwnd = post_window_hwnd
        self.expose_post_window_hwnd = expose_post_window_hwnd
        self.add_calls = 0

    def Add(self):
        self.add_calls += 1
        if self.add_error:
            raise self.add_error
        if self.post_documents is None:
            self.items = [self.document]
        else:
            self.items = list(self.post_documents)
        self.application.Windows = FakeCollection([
            FakeComWindow(
                self.post_window_hwnd,
                expose_hwnd=self.expose_post_window_hwnd,
            )
            for _ in range(self.post_window_count)
        ])
        return self.document


class FakeRange:
    def __init__(self, *, start=0, end=2, insert_error=None):
        self.Start = start
        self.End = end
        self.insertions = []
        self.insert_error = insert_error

    def InsertAfter(self, payload):
        self.insertions.append(payload)
        if self.insert_error:
            raise self.insert_error


class FakeComWindow:
    def __init__(
        self,
        hwnd=101,
        *,
        expose_hwnd=True,
        activate_error=None,
    ):
        if expose_hwnd:
            self.Hwnd = hwnd
        self.activate_error = activate_error
        self.activate_calls = 0

    def Activate(self):
        self.activate_calls += 1
        if self.activate_error:
            raise self.activate_error


class FakeDocument:
    def __init__(
        self,
        *,
        content=None,
        read_only=False,
        protection_type=-1,
        window_count=1,
        window_hwnd=101,
        expose_window_hwnd=True,
        window_activate_error=None,
    ):
        self.Content = content or FakeRange()
        self.ReadOnly = read_only
        self.ProtectionType = protection_type
        self.Windows = FakeCollection([
            FakeComWindow(
                window_hwnd,
                expose_hwnd=expose_window_hwnd,
                activate_error=window_activate_error,
            )
            for _ in range(window_count)
        ])


class FakeApplication:
    def __init__(
        self,
        *,
        documents=None,
        window_count=1,
        window_hwnd=101,
        expose_window_hwnd=True,
        protected_view_count=0,
    ):
        if documents is None:
            documents = [FakeDocument()]
        self.Documents = FakeCollection(documents)
        self.Windows = FakeCollection([
            FakeComWindow(window_hwnd, expose_hwnd=expose_window_hwnd)
            for _ in range(window_count)
        ])
        self.ProtectedViewWindows = FakeCollection(
            [object()] * protected_view_count
        )


class FakeNativeWindow:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def is_enabled(self):
        return self.enabled


def make_adapter(
    *,
    application=None,
    handles=None,
    enabled=True,
    get_active_error=None,
    readiness_timeout=0,
    sleep=None,
):
    application = application or FakeApplication()
    handles = [101] if handles is None else handles
    runtime = FakeRuntime()
    active_calls = []

    def get_active_object(progid):
        active_calls.append(progid)
        if get_active_error:
            raise get_active_error
        return application

    adapter = ComWordAdapter(
        find_handles=lambda: list(handles),
        wrap_window=lambda hwnd: FakeNativeWindow(enabled),
        get_active_object=get_active_object,
        com_runtime=runtime,
        com_error_type=FakeComError,
        clock=lambda: 0,
        sleep=sleep or (lambda seconds: None),
        readiness_timeout=readiness_timeout,
        poll_interval=0.01,
    )
    return adapter, runtime, active_calls


def make_creation_application(
    *,
    document=None,
    add_error=None,
    post_documents=None,
    post_window_count=1,
    post_window_hwnd=101,
    expose_post_window_hwnd=True,
):
    document = document or FakeDocument()
    application = FakeApplication(documents=[], window_count=0)
    documents = FakeDocuments(
        application,
        document,
        add_error=add_error,
        post_documents=post_documents,
        post_window_count=post_window_count,
        post_window_hwnd=post_window_hwnd,
        expose_post_window_hwnd=expose_post_window_hwnd,
    )
    application.Documents = documents
    return application, document, documents


def assert_failure(adapter, reason):
    with pytest.raises(WordAdapterError) as caught:
        adapter.write_text("hello", "append")
    assert caught.value.reason == reason


def test_append_uses_only_content_insert_after():
    document = FakeDocument(content=FakeRange(start=0, end=6))
    application = FakeApplication(documents=[document])
    adapter, runtime, active_calls = make_adapter(
        application=application
    )
    adapter.write_text("Hello 😀", "append")
    assert not hasattr(application, "Hwnd")
    assert document.Content.insertions == ["Hello 😀"]
    assert active_calls == ["Word.Application"]
    assert runtime.initialized == runtime.uninitialized == 1


def test_new_paragraph_prepends_one_word_paragraph_mark():
    document = FakeDocument(content=FakeRange(start=0, end=6))
    adapter, _, _ = make_adapter(
        application=FakeApplication(documents=[document])
    )
    adapter.write_text("World", "new_paragraph")
    assert document.Content.insertions == ["\rWorld"]


def test_new_paragraph_empty_document_has_no_leading_mark():
    document = FakeDocument(content=FakeRange(start=0, end=1))
    adapter, _, _ = make_adapter(
        application=FakeApplication(documents=[document])
    )
    adapter.write_text("Hello", "new_paragraph")
    assert document.Content.insertions == ["Hello"]


def test_word_not_running():
    adapter, runtime, active_calls = make_adapter(handles=[])
    assert_failure(adapter, "word_not_open")
    assert active_calls == []
    assert runtime.initialized == runtime.uninitialized == 1


def test_multiple_word_windows_are_rejected_before_com():
    adapter, _, active_calls = make_adapter(handles=[101, 202])
    assert_failure(adapter, "ambiguous_word_target")
    assert active_calls == []


def test_application_window_hwnd_mismatch_is_rejected_before_write():
    document = FakeDocument()
    adapter, _, _ = make_adapter(
        application=FakeApplication(
            documents=[document],
            window_hwnd=202,
        )
    )
    assert_failure(adapter, "application_window_hwnd_mismatch")
    assert document.Content.insertions == []


def test_document_window_hwnd_mismatch_is_rejected_before_write():
    document = FakeDocument(window_hwnd=202)
    adapter, _, _ = make_adapter(
        application=FakeApplication(documents=[document])
    )
    assert_failure(adapter, "document_window_hwnd_mismatch")
    assert document.Content.insertions == []


@pytest.mark.parametrize("source", ["application", "document"])
def test_unavailable_window_hwnd_is_rejected_before_write(source):
    document = FakeDocument(expose_window_hwnd=source != "document")
    application = FakeApplication(
        documents=[document],
        expose_window_hwnd=source != "application",
    )
    adapter, _, _ = make_adapter(application=application)
    assert_failure(adapter, f"{source}_window_hwnd_unavailable")
    assert document.Content.insertions == []


def test_valid_triple_hwnd_match_allows_write_without_application_hwnd():
    document = FakeDocument(window_hwnd=101)
    application = FakeApplication(documents=[document], window_hwnd=101)
    assert not hasattr(application, "Hwnd")
    adapter, _, _ = make_adapter(application=application, handles=[101])
    adapter.write_text("matched", "append")
    assert document.Content.insertions == ["matched"]


def test_zero_documents_is_rejected():
    adapter, _, _ = make_adapter(
        application=FakeApplication(documents=[])
    )
    assert_failure(adapter, "no_document")


def test_multiple_documents_are_rejected():
    adapter, _, _ = make_adapter(
        application=FakeApplication(
            documents=[FakeDocument(), FakeDocument()]
        )
    )
    assert_failure(adapter, "ambiguous_documents")


@pytest.mark.parametrize(
    "application",
    [
        FakeApplication(window_count=2),
        FakeApplication(documents=[FakeDocument(window_count=2)]),
    ],
)
def test_multiple_document_windows_are_rejected(application):
    adapter, _, _ = make_adapter(application=application)
    assert_failure(adapter, "ambiguous_document_windows")


def test_read_only_document_is_rejected():
    adapter, _, _ = make_adapter(
        application=FakeApplication(
            documents=[FakeDocument(read_only=True)]
        )
    )
    assert_failure(adapter, "read_only_document")


def test_protected_document_is_rejected():
    adapter, _, _ = make_adapter(
        application=FakeApplication(
            documents=[FakeDocument(protection_type=0)]
        )
    )
    assert_failure(adapter, "protected_document")


def test_protected_view_is_rejected():
    adapter, _, _ = make_adapter(
        application=FakeApplication(protected_view_count=1)
    )
    assert_failure(adapter, "protected_view")


def test_disabled_or_modal_window_is_rejected():
    adapter, _, active_calls = make_adapter(enabled=False)
    assert_failure(adapter, "disabled_or_modal")
    assert active_calls == []


def test_com_busy_error_is_handled_and_balanced():
    adapter, runtime, _ = make_adapter(
        get_active_error=FakeComError("busy")
    )
    assert_failure(adapter, "word_not_ready")
    assert runtime.initialized == runtime.uninitialized == 1


def test_startup_readiness_poll_is_bounded_and_testable():
    states = iter([[], [101]])
    sleeps = []
    application = FakeApplication()
    runtime = FakeRuntime()
    adapter = ComWordAdapter(
        find_handles=lambda: next(states),
        wrap_window=lambda hwnd: FakeNativeWindow(),
        get_active_object=lambda progid: application,
        com_runtime=runtime,
        com_error_type=FakeComError,
        clock=lambda: 0,
        sleep=lambda seconds: sleeps.append(seconds),
        readiness_timeout=3,
        poll_interval=0.1,
    )
    adapter.write_text("ready", "append")
    assert sleeps == [0.1]
    assert application.Documents.Item(1).Content.insertions == ["ready"]


def test_invalid_mode_never_initializes_com():
    adapter, runtime, active_calls = make_adapter()
    with pytest.raises(WordAdapterError) as caught:
        adapter.write_text("hello", "replace")
    assert caught.value.reason == "invalid_mode"
    assert runtime.initialized == runtime.uninitialized == 0
    assert active_calls == []


def test_range_exposes_no_document_text_to_adapter():
    """FakeRange intentionally has positions and insertion only, no text."""
    document = FakeDocument(content=FakeRange(start=0, end=2))
    adapter, _, _ = make_adapter(
        application=FakeApplication(documents=[document])
    )
    adapter.write_text("safe", "append")
    assert document.Content.insertions == ["safe"]


def test_write_error_is_attempted_once_and_reported_as_unconfirmed():
    content = FakeRange(insert_error=FakeComError("write failed"))
    document = FakeDocument(content=content)
    adapter, runtime, _ = make_adapter(
        application=FakeApplication(documents=[document])
    )
    with pytest.raises(WordAdapterError) as caught:
        adapter.write_text("once", "append")
    assert caught.value.outcome == WRITE_FAILED
    assert content.insertions == ["once"]
    assert runtime.initialized == runtime.uninitialized == 1


def assert_creation_failure(adapter, reason, outcome=None):
    with pytest.raises(WordAdapterError) as caught:
        adapter.create_document()
    assert caught.value.reason == reason
    if outcome is not None:
        assert caught.value.outcome == outcome
    return caught.value


def test_create_document_word_not_running():
    adapter, runtime, active_calls = make_adapter(handles=[])
    assert_creation_failure(adapter, "word_not_open")
    assert active_calls == []
    assert runtime.initialized == runtime.uninitialized == 1


def test_safe_empty_word_application_creates_one_document_once():
    application, document, documents = make_creation_application()
    adapter, runtime, _ = make_adapter(application=application)
    adapter.create_document()
    assert documents.add_calls == 1
    assert application.Documents.Count == 1
    assert application.Documents.Item(1) is document
    assert document.Windows.Item(1).activate_calls == 1
    assert runtime.initialized == runtime.uninitialized == 1


def test_create_refuses_when_document_is_already_open():
    document = FakeDocument()
    application = FakeApplication(documents=[document])
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(adapter, "document_already_open")
    assert not hasattr(application.Documents, "add_calls")


def test_create_rejects_multiple_native_targets_before_com():
    adapter, _, active_calls = make_adapter(handles=[101, 202])
    assert_creation_failure(adapter, "ambiguous_word_target")
    assert active_calls == []


def test_create_com_attachment_failure_is_bounded():
    adapter, runtime, _ = make_adapter(
        get_active_error=FakeComError("not ready")
    )
    error = assert_creation_failure(
        adapter,
        "word_not_ready",
        ATTACHMENT_FAILED,
    )
    assert error.outcome == ATTACHMENT_FAILED
    assert runtime.initialized == runtime.uninitialized == 1


def test_create_poll_retries_attachment_readiness_but_adds_once():
    application, _, documents = make_creation_application()
    runtime = FakeRuntime()
    active_calls = 0
    sleeps = []

    def get_active_object(progid):
        nonlocal active_calls
        active_calls += 1
        if active_calls == 1:
            raise FakeComError("not ready")
        return application

    adapter = ComWordAdapter(
        find_handles=lambda: [101],
        wrap_window=lambda hwnd: FakeNativeWindow(),
        get_active_object=get_active_object,
        com_runtime=runtime,
        com_error_type=FakeComError,
        clock=lambda: 0,
        sleep=lambda seconds: sleeps.append(seconds),
        readiness_timeout=3,
        poll_interval=0.1,
    )
    adapter.create_document()
    assert active_calls == 2
    assert sleeps == [0.1]
    assert documents.add_calls == 1


def test_create_rejects_ambiguous_pre_creation_window_state():
    application, _, documents = make_creation_application()
    application.Windows = FakeCollection([FakeComWindow(101)])
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(adapter, "ambiguous_pre_creation_windows")
    assert documents.add_calls == 0


def test_create_rejects_protected_view_before_add():
    application = FakeApplication(
        documents=[],
        window_count=0,
        protected_view_count=1,
    )
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(adapter, "protected_view")


def test_create_rejects_disabled_target_before_com():
    application, document, documents = make_creation_application()
    adapter, _, active_calls = make_adapter(
        application=application,
        enabled=False,
    )
    assert_creation_failure(adapter, "disabled_or_modal")
    assert documents.add_calls == 0
    assert document.Windows.Item(1).activate_calls == 0
    assert active_calls == []


def test_documents_add_exception_is_never_retried():
    application, _, documents = make_creation_application(
        add_error=FakeComError("uncertain")
    )
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(adapter, "creation_error", CREATION_FAILED)
    assert documents.add_calls == 1


def test_post_creation_document_count_is_unconfirmed():
    application, _, documents = make_creation_application(post_documents=[])
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(
        adapter,
        "post_creation_validation_failed",
        CREATION_UNCONFIRMED,
    )
    assert documents.add_calls == 1


def test_post_creation_application_window_count_is_unconfirmed():
    application, _, documents = make_creation_application(
        post_window_count=2
    )
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(
        adapter,
        "post_creation_validation_failed",
        CREATION_UNCONFIRMED,
    )
    assert documents.add_calls == 1


def test_post_creation_application_hwnd_mismatch_is_unconfirmed():
    application, document, documents = make_creation_application(
        post_window_hwnd=202
    )
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(
        adapter,
        "post_creation_validation_failed",
        CREATION_UNCONFIRMED,
    )
    assert documents.add_calls == 1
    assert document.Windows.Item(1).activate_calls == 0


def test_post_creation_document_hwnd_mismatch_is_unconfirmed():
    document = FakeDocument(window_hwnd=202)
    application, _, documents = make_creation_application(document=document)
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(
        adapter,
        "post_creation_validation_failed",
        CREATION_UNCONFIRMED,
    )
    assert documents.add_calls == 1
    assert document.Windows.Item(1).activate_calls == 0


@pytest.mark.parametrize(
    "document",
    [
        FakeDocument(read_only=True),
        FakeDocument(protection_type=0),
    ],
)
def test_unsafe_created_document_is_unconfirmed(document):
    application, _, documents = make_creation_application(document=document)
    adapter, _, _ = make_adapter(application=application)
    assert_creation_failure(
        adapter,
        "post_creation_validation_failed",
        CREATION_UNCONFIRMED,
    )
    assert documents.add_calls == 1


def test_valid_created_document_triple_hwnd_match_succeeds():
    document = FakeDocument(window_hwnd=101)
    application, _, documents = make_creation_application(
        document=document,
        post_window_hwnd=101,
    )
    adapter, _, _ = make_adapter(application=application, handles=[101])
    adapter.create_document()
    assert documents.add_calls == 1
    assert application.Windows.Item(1).Hwnd == 101
    assert document.Windows.Item(1).Hwnd == 101
    assert document.Windows.Item(1).activate_calls == 1


def test_created_document_window_activation_failure_is_partial_success():
    document = FakeDocument(
        window_hwnd=101,
        window_activate_error=FakeComError("cannot activate"),
    )
    application, _, documents = make_creation_application(document=document)
    adapter, _, _ = make_adapter(application=application)
    error = assert_creation_failure(
        adapter,
        "document_window_activation_failed",
        CREATION_ACTIVATION_FAILED,
    )
    assert "was created" in error.user_message
    assert documents.add_calls == 1
    assert document.Windows.Item(1).activate_calls == 1
