import telegram_client as tc

SAMPLE_TAGGED = [
    "Mountain_trail_walk_recording_a1b2c3d4e5f60718_part01of04.mp4",
    "Mountain_trail_walk_recording_a1b2c3d4e5f60718_part02of04.mp4",
    "Mountain_trail_walk_recording_a1b2c3d4e5f60718_part03of04.mp4",
    "Mountain_trail_walk_recording_a1b2c3d4e5f60718_part04of04.mp4",
    "Holiday_photos_part_3_Day,_Night_0f1e2d3c4b5a6978_part01of02.mp4",
    "Holiday_photos_part_3_Day,_Night_0f1e2d3c4b5a6978_part02of02.mp4",
]
SAMPLE_TRUNCATED = [
    "QUARTERLY_REPORT_SLIDES_AND_NOTES_FOR_THE_TEAM_MEETING_1a2b3c4d5e6f7081.mp4",
    "Lecture_recording_with_a_very_long_descriptive_title_90abcdef12345678.mp4",
]
SAMPLE_SINGLES = [
    "Summer Holiday Highlights Reel.mp4",
    "Interview with the Lead Engineer.mp4",
    "Conference Stream VOD (From 11-19) 720p.mp4",
    "cat naps on the keyboard again.mp4",
]

def test_underscore_separated_chunks_are_recognised():
    for name in SAMPLE_TAGGED:
        m = tc._TAGGED_CHUNK_NAME_RE.match(name)
        assert m, f"not recognised as a chunk: {name}"
        assert len(m.group(2)) == 16
        assert 1 <= int(m.group(3)) <= int(m.group(4))
        assert m.group(5) == ".mp4"

def test_the_dotted_form_the_uploader_writes_still_matches():

    m = tc._TAGGED_CHUNK_NAME_RE.match("clip.a1b2c3d4e5f60718.part01of04.mp4")
    assert m and m.group(1) == "clip" and m.group(2) == "a1b2c3d4e5f60718"

def test_the_four_parts_group_as_one_file():

    groups = {}
    for name in SAMPLE_TAGGED:
        m = tc._TAGGED_CHUNK_NAME_RE.match(name)
        groups.setdefault((m.group(1), m.group(2), int(m.group(4)), m.group(5)), []).append(
            int(m.group(3)))
    assert len(groups) == 2, groups
    by_total = {k[2]: sorted(v) for k, v in groups.items()}
    assert by_total[4] == [1, 2, 3, 4]
    assert by_total[2] == [1, 2]

def test_truncated_names_are_caught_by_the_tag():

    for name in SAMPLE_TRUNCATED:
        assert tc._TAGGED_CHUNK_NAME_RE.match(name) is None
        m = tc._TAGGED_CHUNK_NO_PART_RE.match(name)
        assert m, f"truncated chunk not recognised: {name}"
        assert len(m.group(2)) == 16

def test_truncated_parts_of_one_file_share_a_key():
    keys = set()
    for name in SAMPLE_TRUNCATED:
        m = tc._TAGGED_CHUNK_NO_PART_RE.match(name)
        keys.add((m.group(1), m.group(2), m.group(3)))

    assert len(keys) == 2

def test_ordinary_filenames_are_not_mistaken_for_chunks():

    for name in SAMPLE_SINGLES:
        assert tc._TAGGED_CHUNK_NAME_RE.match(name) is None, name
        assert tc._LEGACY_CHUNK_NAME_RE.match(name) is None, name
        assert tc._TAGGED_CHUNK_NO_PART_RE.match(name) is None, name

def test_a_hex_like_name_that_is_not_a_tag_is_left_alone():

    for name in ["report_2026.mp4", "clip_deadbeef.mp4",
                 "clip_a1b2c3d4e5f60718XY.mp4",
                 "clip_zzzzzzzzzzzzzzzz.mp4"]:
        assert tc._TAGGED_CHUNK_NO_PART_RE.match(name) is None, name

def test_legacy_untagged_chunks_still_work_both_ways():
    for name in ["old_style.part02of03.mkv", "old_style_part02of03.mkv"]:
        m = tc._LEGACY_CHUNK_NAME_RE.match(name)
        assert m, name
        assert int(m.group(2)) == 2 and int(m.group(3)) == 3

def test_generated_chunk_names_stay_within_the_safe_length():

    long_base = "A" * 300
    for parts in (2, 10, 99):
        for ext in (".mp4", ".webm", ".x"):
            name = tc._chunk_part_name(long_base, "1a2b3c4d5e6f7081", 0, parts, ext)
            stem = name[:-len(ext)]
            assert len(stem) <= tc._MAX_CHUNK_STEM_LENGTH, f"{len(stem)}: {name}"
            assert name.endswith(ext)

def test_trimming_takes_it_out_of_the_base_never_the_marker():

    name = tc._chunk_part_name("B" * 300, "1a2b3c4d5e6f7081", 6, 12, ".mp4")
    assert name.endswith(".1a2b3c4d5e6f7081.part07of12.mp4"), name
    m = tc._TAGGED_CHUNK_NAME_RE.match(name)
    assert m and m.group(2) == "1a2b3c4d5e6f7081"
    assert int(m.group(3)) == 7 and int(m.group(4)) == 12

def test_generated_names_round_trip_through_the_chunk_pattern():

    for base in ["short", "a name with spaces", "C" * 200, "dots.in.the.name"]:
        name = tc._chunk_part_name(base, "aabbccddeeff0011", 0, 3, ".mkv")
        assert tc._TAGGED_CHUNK_NAME_RE.match(name), name

        stem, _, ext = name.rpartition(".")
        assert tc._TAGGED_CHUNK_NAME_RE.match(stem.replace(".", "_") + "." + ext), name

def test_short_names_are_left_alone():
    assert tc._chunk_part_name("clip", "aabbccddeeff0011", 0, 2, ".mp4") == \
        "clip.aabbccddeeff0011.part01of02.mp4"

def test_an_absurd_extension_still_yields_a_usable_marker():

    name = tc._chunk_part_name("base", "aabbccddeeff0011", 0, 2, "." + "x" * 60)
    assert "aabbccddeeff0011" in name and "part01of02" in name

def test_index_shape_summarises_without_leaking_names():

    import shared

    shape = shared._index_shape()
    assert "files" in shape and "folders" in shape
    assert ".mp4" not in shape and "/" not in shape

def test_index_shape_never_raises(monkeypatch):

    import shared
    import store as store_mod

    monkeypatch.setattr(store_mod, "load_files", lambda: (_ for _ in ()).throw(RuntimeError("db gone")))
    assert shared._index_shape() == "unavailable"
