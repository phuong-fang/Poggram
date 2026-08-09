import math

import pytest

import telegram_client as tc

CANDIDATE_REQUESTS = list(range(0, 513, 32)) + [1, 100, 200, 300, 511, 513, 1024, -5]

FILE_SIZES = [
    1, 1024, 10 * 1024 * 1024,
    100 * 1024 * 1024 - 1, 100 * 1024 * 1024,
    256 * 1024 * 1024,
    750 * 1024 * 1024, 750 * 1024 * 1024 + 1,
    1_900_000_000,
    2_097_152_000,
    3_900_000_000,
    4_194_304_000,
]

@pytest.mark.parametrize("premium", [False, True])
def test_every_selectable_part_size_obeys_the_documented_rules(premium):
    max_parts = 8000 if premium else 4000
    for total in FILE_SIZES:
        for requested in CANDIDATE_REQUESTS:
            part = tc._select_part_size(total, requested, premium)
            if part is None:
                continue
            assert part % 1024 == 0, (total, requested, part)
            assert 524288 % part == 0, (total, requested, part)
            assert part <= 524288, (total, requested, part)
            assert math.ceil(total / part) <= max_parts, (total, requested, part)

def test_an_illegal_request_is_snapped_down_not_passed_through():

    assert tc._snap_part_size_kb(100) == 64
    assert tc._snap_part_size_kb(96) == 64
    assert tc._snap_part_size_kb(480) == 256
    assert tc._snap_part_size_kb(512) == 512
    assert tc._snap_part_size_kb(1) == 32
    assert tc._snap_part_size_kb(100000) == 512

def test_the_doubling_loop_cannot_exceed_the_cap():

    for kb in (300, 400, 500):
        part = tc._select_part_size(1_900_000_000, kb, False)
        assert part is not None and part <= 524288, (kb, part)

def test_the_valid_set_is_exactly_the_powers_of_two_that_divide_512():
    derived = tuple(kb for kb in range(1, 513) if (kb * 1024) % 1024 == 0
                    and 524288 % (kb * 1024) == 0 and kb >= 32)
    assert tc.VALID_PART_SIZES_KB == derived

@pytest.mark.parametrize("premium,expected_ceiling", [
    (False, 4000 * 524288),
    (True, 8000 * 524288),
])
def test_the_per_message_ceiling_matches_the_documented_file_size_limits(premium, expected_ceiling):

    assert tc._select_part_size(expected_ceiling, 0, premium) == 524288
    assert tc._select_part_size(expected_ceiling + 1, 0, premium) is None

def test_auto_tiers_still_pick_the_documented_sizes():

    assert tc._select_part_size(50 * 1024 * 1024, 0, False) == 64 * 1024
    assert tc._select_part_size(500 * 1024 * 1024, 0, False) == 256 * 1024
    assert tc._select_part_size(1_000_000_000, 0, False) == 512 * 1024
