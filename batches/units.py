import re
from fractions import Fraction


_READING = re.compile(r'[+-]?[0-9]+(?:/[0-9]+|\.[0-9]+)?')


def require_identifier(value, field):
    if not isinstance(value, str) or not value or value.strip() != value or not value.isprintable():
        raise ValueError(f'invalid {field}')
    return value


def parse_um(value):
    """Interpret a decimal or rational reading without a binary float conversion."""
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if not isinstance(value, str) or _READING.fullmatch(value.strip()) is None:
        raise ValueError('expected an integer, exact decimal or fraction')
    try:
        return Fraction(value.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('invalid rational reading') from exc


def encode_fraction(value):
    if not isinstance(value, Fraction):
        raise ValueError('expected a Fraction for exchange')
    return f'{value.numerator}/{value.denominator}'


def decode_fraction(value):
    if not isinstance(value, str):
        raise ValueError('encoded fraction requires text')
    result = parse_um(value)
    if value != encode_fraction(result):
        raise ValueError('encoded fraction must have reduced n/d form')
    return result
