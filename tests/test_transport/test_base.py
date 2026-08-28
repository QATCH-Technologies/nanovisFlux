"""Transport (abstract base): the default reset_input_buffer no-op, the
context-manager protocol (__enter__/__exit__ delegating to open/close), and
the abstract open()/close() hook bodies themselves.

SerialTransport and SimulatedTransport both fully replace open()/close()
without ever calling back into the base class's own stub bodies, so a
minimal concrete subclass is defined here to reach those directly."""

import pytest

from src.transport.base import Transport


class _RecordingTransport(Transport):
    """Concrete Transport whose open()/close() just record that they ran,
    so context-manager tests can assert on observable state."""

    def __init__(self):
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def write_line(self, line: str) -> None:
        pass

    def read_line(self, timeout: float | None = None) -> str:
        return ""


def test_transport_cannot_be_instantiated_directly():
    """ABC enforcement: open/close/write_line/read_line are all abstract,
    so the base class itself must refuse instantiation."""
    with pytest.raises(TypeError):
        Transport()


def test_default_open_and_close_hook_bodies_are_inert_no_ops():
    """The abstract base's own open()/close() bodies exist only to carry
    documentation for subclasses -- calling them directly (as a subclass
    layering extra setup around super().open()/close() naturally would)
    must be a harmless no-op rather than raising."""
    t = _RecordingTransport()
    assert Transport.open(t) is None
    assert Transport.close(t) is None


def test_default_reset_input_buffer_is_a_noop():
    t = _RecordingTransport()
    assert t.reset_input_buffer() is None  # base default: nothing to flush


def test_context_manager_enter_opens_and_returns_the_transport():
    t = _RecordingTransport()

    with t as entered:
        assert entered is t
        assert t.opened is True
        assert t.closed is False


def test_context_manager_exit_closes_even_when_the_body_raises():
    t = _RecordingTransport()

    with pytest.raises(ValueError):
        with t:
            assert t.opened is True
            raise ValueError("boom")

    assert t.closed is True
