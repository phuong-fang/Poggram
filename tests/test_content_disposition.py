import pytest

from routes_streaming import _content_disposition

def _encodable(value):

    value.encode("latin-1")
    return True

@pytest.mark.parametrize("name", [
    "ホタル.mp4",
    "Кириллица.webm",
    "简体中文.mkv",
    "Café Übung.mkv",
    "emoji 🎬 clip.mp4",
    "plain-ascii.mp4",
    "no-extension",
    "ホタル",
    'quote".mp4',
    "back\\slash.mp4",
])
def test_header_is_always_latin1_encodable(name):
    assert _encodable(_content_disposition(name))

def test_the_real_name_survives_in_the_extended_field():
    value = _content_disposition("ホタル.mp4")

    assert "filename*=UTF-8''%E3%83%9B%E3%82%BF%E3%83%AB.mp4" in value

def test_ascii_fallback_keeps_the_extension():

    assert 'filename="download.mp4"' in _content_disposition("ホタル.mp4")

def test_accented_latin_degrades_to_its_plain_form():

    assert 'filename="Cafe Ubung.mkv"' in _content_disposition("Café Übung.mkv")

def test_plain_ascii_names_are_unchanged():
    value = _content_disposition("plain-ascii.mp4")
    assert 'filename="plain-ascii.mp4"' in value
    assert "filename*=UTF-8''plain-ascii.mp4" in value

def test_quotes_and_backslashes_cannot_break_out_of_the_quoted_string():

    value = _content_disposition('quote".mp4')
    fallback = value.split('filename="')[1].split('"')[0]
    assert '"' not in fallback and "\\" not in fallback

    assert "%22" in value

def test_both_serving_paths_use_the_helper():

    import re

    with open("routes_streaming.py", encoding="utf-8") as f:
        source = f.read()
    assert source.count('"Content-Disposition": _content_disposition(') == 2
    assert not re.search(r'Content-Disposition["\']\s*:\s*f?[\'"]attachment; filename="\{', source)
