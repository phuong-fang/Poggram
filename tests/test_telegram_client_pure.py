import telegram_client

def test_select_part_size_small_file_uses_64kb_tier():
    size = 50 * 1024 * 1024
    assert telegram_client._select_part_size(size, 0, is_premium=False) == 64 * 1024

def test_select_part_size_medium_file_uses_256kb_tier():
    size = 500 * 1024 * 1024
    assert telegram_client._select_part_size(size, 0, is_premium=False) == 256 * 1024

def test_select_part_size_large_file_uses_512kb_tier():
    size = 1_000 * 1024 * 1024
    assert telegram_client._select_part_size(size, 0, is_premium=False) == 512 * 1024

def test_select_part_size_explicit_request_is_honored_within_cap():
    size = 10 * 1024 * 1024
    assert telegram_client._select_part_size(size, 128, is_premium=False) == 128 * 1024

def test_select_part_size_explicit_request_capped_at_512kb():

    size = 10 * 1024 * 1024
    assert telegram_client._select_part_size(size, 1024, is_premium=False) == 512 * 1024

def test_select_part_size_bumps_tier_to_stay_under_free_part_count_cap():

    size = 300 * 1024 * 1024
    result = telegram_client._select_part_size(size, 64, is_premium=False)
    max_parts = 4000
    assert result is not None
    import math
    assert math.ceil(size / result) <= max_parts

def test_select_part_size_premium_allows_more_parts_at_smaller_size():

    size = 300 * 1024 * 1024
    free_result = telegram_client._select_part_size(size, 64, is_premium=False)
    premium_result = telegram_client._select_part_size(size, 64, is_premium=True)
    assert premium_result <= free_result

def test_select_part_size_returns_none_when_even_512kb_parts_dont_fit():

    huge_size = 4000 * 512 * 1024 + 1
    assert telegram_client._select_part_size(huge_size, 0, is_premium=False) is None

def test_select_part_size_premium_fits_where_free_does_not():
    huge_size = 4000 * 512 * 1024 + 1
    assert telegram_client._select_part_size(huge_size, 0, is_premium=True) is not None
