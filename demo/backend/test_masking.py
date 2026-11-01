from masking import mask, unmask


def test_same_value_same_placeholder_and_roundtrip():
    text = "Иванов звонил, потом Иванов писал на a@b.ru, а Петров молчал."
    results = [
        {"entity_type": "PERSON", "start": 0, "end": 6, "score": 0.85},
        {"entity_type": "PERSON", "start": 21, "end": 27, "score": 0.85},
        {"entity_type": "EMAIL_ADDRESS", "start": 37, "end": 43, "score": 1.0},
        {"entity_type": "PERSON", "start": 47, "end": 53, "score": 0.85},
    ]
    m = mask(text, results)
    assert m.text == "<PERSON_1> звонил, потом <PERSON_1> писал на <EMAIL_ADDRESS_1>, а <PERSON_2> молчал."
    assert unmask(m.text, m.mapping) == text


def test_overlap_keeps_best_span():
    text = "token sk-abcdefghijklmnopqrstuvwxyz"
    results = [
        {"entity_type": "SECRET", "start": 6, "end": 35, "score": 0.85},
        {"entity_type": "RU_PASSPORT", "start": 9, "end": 15, "score": 0.3},
    ]
    m = mask(text, results)
    assert m.text == "token <SECRET_1>"


def test_unmask_longest_first():
    mapping = {"<PERSON_1>": "A", "<PERSON_10>": "B"}
    assert unmask("<PERSON_10> and <PERSON_1>", mapping) == "B and A"


def test_unmask_tolerates_rewritten_brackets():
    mapping = {"<PERSON_1>": "Иванов", "<PHONE_NUMBER_2>": "+7 912 345-67-89"}
    assert unmask("Здравствуйте, [PERSON_1], ваш телефон +[PHONE_NUMBER_2] и PERSON_1.", mapping) == \
        "Здравствуйте, Иванов, ваш телефон ++7 912 345-67-89 и Иванов."
    assert unmask("нет заглушек тут", mapping) == "нет заглушек тут"
