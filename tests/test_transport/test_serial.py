"""SerialTransport: the pyserial-backed Transport implementation. pyserial is
imported lazily inside open(), so every test here patches serial.Serial
before calling .open() rather than patching SerialTransport's own module
(it has no module-level `serial` name to patch)."""

from unittest.mock import MagicMock, patch

import pytest

from src.transport.serial import SerialTransport


def _opened_transport(mock_ser: MagicMock) -> SerialTransport:
    with patch("serial.Serial", return_value=mock_ser) as ctor:
        transport = SerialTransport("COM3", baudrate=9600, timeout=2.5)
        transport.open()
    ctor.assert_called_once_with("COM3", 9600, timeout=2.5)
    return transport


def test_open_constructs_pyserial_with_configured_parameters():
    mock_ser = MagicMock()
    transport = _opened_transport(mock_ser)
    assert transport._ser is mock_ser


def test_write_line_encodes_ascii_and_appends_newline():
    mock_ser = MagicMock()
    transport = _opened_transport(mock_ser)

    transport.write_line("G1 X100 F500")

    mock_ser.write.assert_called_once_with(b"G1 X100 F500\n")


def test_write_line_raises_when_not_open():
    transport = SerialTransport("COM3")
    with pytest.raises(AssertionError):
        transport.write_line("G0")


def test_read_line_decodes_and_strips_without_timeout_override():
    mock_ser = MagicMock()
    mock_ser.readline.return_value = b"  ok  \r\n"
    mock_ser.timeout = 2.5
    transport = _opened_transport(mock_ser)

    result = transport.read_line()

    assert result == "ok"
    assert mock_ser.timeout == 2.5  # unchanged: no override was requested


def test_read_line_applies_timeout_override_before_reading():
    mock_ser = MagicMock()
    mock_ser.readline.return_value = b"ok\n"
    transport = _opened_transport(mock_ser)

    transport.read_line(timeout=0.5)

    assert mock_ser.timeout == 0.5


def test_read_line_replaces_invalid_ascii_bytes_instead_of_raising():
    mock_ser = MagicMock()
    mock_ser.readline.return_value = b"[PRB:1,2,3]\xff\n"
    transport = _opened_transport(mock_ser)

    result = transport.read_line()

    assert result.startswith("[PRB:1,2,3]")
    assert "�" in result  # invalid byte replaced, not dropped or raised


def test_read_line_raises_when_not_open():
    transport = SerialTransport("COM3")
    with pytest.raises(AssertionError):
        transport.read_line()


def test_reset_input_buffer_delegates_to_pyserial():
    mock_ser = MagicMock()
    transport = _opened_transport(mock_ser)

    transport.reset_input_buffer()

    mock_ser.reset_input_buffer.assert_called_once_with()


def test_reset_input_buffer_is_a_noop_when_never_opened():
    transport = SerialTransport("COM3")
    transport.reset_input_buffer()  # must not raise


def test_close_is_a_noop_when_never_opened():
    transport = SerialTransport("COM3")
    transport.close()  # must not raise
    assert transport._ser is None


def test_close_closes_pyserial_and_clears_reference():
    mock_ser = MagicMock()
    transport = _opened_transport(mock_ser)

    transport.close()

    mock_ser.close.assert_called_once_with()
    assert transport._ser is None


def test_close_is_safe_to_call_twice():
    mock_ser = MagicMock()
    transport = _opened_transport(mock_ser)

    transport.close()
    transport.close()  # second call must not raise or re-close

    mock_ser.close.assert_called_once_with()


def test_context_manager_opens_and_closes():
    mock_ser = MagicMock()
    with patch("serial.Serial", return_value=mock_ser):
        transport = SerialTransport("COM3")
        with transport as opened:
            assert opened is transport
            assert transport._ser is mock_ser
    mock_ser.close.assert_called_once_with()
    assert transport._ser is None
