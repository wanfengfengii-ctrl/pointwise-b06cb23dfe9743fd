from batches.roster import validate_roster
from prediction.package import ForecastPair, ModelReference, PredictionRow, validate_forecast
from training.catalog import ModelVersion


def apply_models(package_id, roster, first, second):
    validate_roster(roster)
    if not isinstance(first, ModelVersion) or not isinstance(second, ModelVersion):
        raise ValueError('two fixed model versions are required')
    first_reference = ModelReference(first.model_id, first.truth_id, first.strategy, first.parameter)
    second_reference = ModelReference(second.model_id, second.truth_id, second.strategy, second.parameter)
    rows = tuple(PredictionRow(piece, first.parameter, second.parameter) for piece in roster.pieces)
    return validate_forecast(ForecastPair(package_id, roster, first_reference, second_reference, rows))
