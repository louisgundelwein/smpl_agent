"""Tests for src.protocol."""

import json

import pytest

from src.protocol import LineBuffer, decode, encode


def test_encode_decode_roundtrip():
    msg = {"type": "run", "content": "hello"}
    encoded = encode(msg)
    assert encoded.endswith(b"\n")
    decoded = decode(encoded.rstrip(b"\n"))
    assert decoded == msg


def test_encode_produces_utf8():
    msg = {"type": "response", "content": "Ü Ä Ö"}
    encoded = encode(msg)
    assert "Ü Ä Ö" in encoded.decode("utf-8")


def test_decode_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        decode(b"not json")


def test_decode_empty_line_raises():
    with pytest.raises(ValueError, match="Empty line"):
        decode(b"  ")


def test_decode_non_dict_raises():
    with pytest.raises(ValueError, match="Expected JSON object"):
        decode(b'[1, 2, 3]')


def test_line_buffer_partial():
    buf = LineBuffer()
    assert buf.feed(b'{"type":') == []
    lines = buf.feed(b'"pong"}\n')
    assert len(lines) == 1
    assert decode(lines[0]) == {"type": "pong"}


def test_line_buffer_multiple():
    buf = LineBuffer()
    lines = buf.feed(b'{"a":1}\n{"b":2}\n')
    assert len(lines) == 2


def test_line_buffer_split_across_feeds():
    buf = LineBuffer()
    assert buf.feed(b'{"type":') == []
    assert buf.feed(b'"pi') == []
    lines = buf.feed(b'ng"}\n')
    assert len(lines) == 1
    assert decode(lines[0]) == {"type": "ping"}


def test_decode_missing_type_raises():
    with pytest.raises(ValueError, match="missing required 'type' field"):
        decode(b'{"key": "value"}')
