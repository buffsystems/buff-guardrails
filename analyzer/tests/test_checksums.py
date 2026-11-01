from buff_guardrails import checksums


def test_luhn_accepts_valid_card_and_rejects_altered():
    assert checksums.luhn("4111111111111111")
    assert checksums.luhn("5500000000000004")
    assert not checksums.luhn("4111111111111112")
    assert not checksums.luhn("abcd")


def test_snils_control_digits():
    assert checksums.snils("11223344595")
    assert not checksums.snils("11223344596")
    assert not checksums.snils("1122334459")


def test_inn_10_and_12():
    assert checksums.inn("7707083893")  # Sberbank
    assert checksums.inn("500100732259")  # person example from the FNS algorithm docs
    assert not checksums.inn("7707083894")
    assert not checksums.inn("500100732258")
    assert not checksums.inn("12345")


def test_ogrn_13_and_15():
    assert checksums.ogrn("1027700132195")  # Sberbank
    assert checksums.ogrn("304500116000157")
    assert not checksums.ogrn("1027700132196")
    assert not checksums.ogrn("304500116000158")
