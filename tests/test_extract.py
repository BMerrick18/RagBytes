from shark_byte.extract.registry import get_extractor


def test_known_suffix_resolves():
    assert get_extractor(".txt") is not None


def test_unknown_suffix_does_not_resolve():
    assert get_extractor(".zip") is None
