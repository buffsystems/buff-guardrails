"""Checksum validators for Russian identifiers and payment cards.

Pure functions over digit strings. Each returns True when the checksum holds,
False when it does not. Callers strip separators before calling.
"""

from __future__ import annotations


def luhn(digits: str) -> bool:
    """Luhn mod-10 check (payment cards, OMS policy numbers)."""
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def snils(digits: str) -> bool:
    """СНИЛС: 9 digits + 2 control digits (ПФР algorithm)."""
    if not digits.isdigit() or len(digits) != 11:
        return False
    number, control = digits[:9], int(digits[9:])
    total = sum(int(d) * (9 - i) for i, d in enumerate(number))
    if total < 100:
        expected = total
    elif total in (100, 101):
        expected = 0
    else:
        expected = total % 101
        if expected == 100:
            expected = 0
    return expected == control


_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_A = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_B = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _weighted(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10


def inn(digits: str) -> bool:
    """ИНН: 10 digits (organisation) or 12 digits (person)."""
    if not digits.isdigit():
        return False
    if len(digits) == 10:
        return _weighted(digits, _INN10) == int(digits[9])
    if len(digits) == 12:
        return _weighted(digits, _INN12_A) == int(digits[10]) and _weighted(
            digits, _INN12_B
        ) == int(digits[11])
    return False


def ogrn(digits: str) -> bool:
    """ОГРН (13 digits) or ОГРНИП (15 digits)."""
    if not digits.isdigit():
        return False
    if len(digits) == 13:
        return int(digits[:12]) % 11 % 10 == int(digits[12])
    if len(digits) == 15:
        return int(digits[:14]) % 13 % 10 == int(digits[14])
    return False
