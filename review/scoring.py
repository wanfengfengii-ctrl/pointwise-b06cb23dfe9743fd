from dataclasses import dataclass
from fractions import Fraction

from review.pairing import PairedPiece


@dataclass(frozen=True, slots=True)
class PieceScore:
    piece_id: str
    first_squared: Fraction
    second_squared: Fraction
    delta: Fraction


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    pieces: tuple[PieceScore, ...]
    mean_delta: Fraction


def _score(piece):
    if not isinstance(piece, PairedPiece) or not all(
        isinstance(value, Fraction) for value in (piece.first, piece.second, piece.actual)
    ):
        raise ValueError('expected a paired piece with exact readings')
    first_squared = (piece.first - piece.actual) ** 2
    second_squared = (piece.second - piece.actual) ** 2
    return PieceScore(piece.piece_id, first_squared, second_squared, first_squared - second_squared)


def score_pieces(pairs):
    pieces = tuple(_score(piece) for piece in pairs)
    if not pieces:
        raise ValueError('score requires at least one paired piece')
    mean_delta = sum((piece.delta for piece in pieces), Fraction(0)) / len(pieces)
    return ScoreSummary(pieces, mean_delta)
