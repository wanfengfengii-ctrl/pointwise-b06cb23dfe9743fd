from dataclasses import dataclass
from fractions import Fraction

from measurements.exchange import validate_truth
from prediction.package import validate_forecast


@dataclass(frozen=True, slots=True)
class PairedPiece:
    piece_id: str
    first: Fraction
    second: Fraction
    actual: Fraction


def pair_for_review(forecast, truth):
    validate_forecast(forecast)
    validate_truth(truth)
    if forecast.roster != truth.roster:
        raise ValueError('forecast and truth require the same frozen roster')
    return tuple(
        PairedPiece(prediction.piece_id, prediction.first, prediction.second, measurement.value)
        for prediction, measurement in zip(forecast.rows, truth.rows, strict=True)
    )
