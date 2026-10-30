from gavekort import codes


def test_new_code_has_expected_format() -> None:
    code = codes.new_code()
    assert codes.is_valid(code)
    assert code.startswith("GK-")
    assert len(code) == len("GK-XXXX-XXXX")


def test_codes_avoid_ambiguous_characters() -> None:
    body = "".join(codes.new_code()[3:].replace("-", "") for _ in range(1000))
    assert not set(body) & set("01OIL")
    assert set(body) <= set(codes.ALPHABET)


def test_codes_are_unique() -> None:
    generated = {codes.new_code() for _ in range(10_000)}
    assert len(generated) == 10_000


def test_is_valid_rejects_malformed_codes() -> None:
    for bad in ("", "GK-ABCD", "GK-ABCD-EFG0", "XX-ABCD-EFGH", "gk-abcd-efgh", "GK-ABCD-EFGH-"):
        assert not codes.is_valid(bad), bad
