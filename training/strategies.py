from fractions import Fraction


LAST_PIECE = 'last_piece'
MEAN = 'mean'


def last_piece_value(rows):
    if not rows:
        raise ValueError('last-piece model requires training rows')
    return rows[-1].value


def mean_piece_value(rows):
    if not rows:
        raise ValueError('mean model requires training rows')
    return sum((row.value for row in rows), Fraction(0)) / len(rows)


STRATEGIES = {LAST_PIECE: last_piece_value, MEAN: mean_piece_value}


def require_strategy(strategy):
    if not isinstance(strategy, str) or strategy not in STRATEGIES:
        raise ValueError('unsupported training strategy')
    return strategy
