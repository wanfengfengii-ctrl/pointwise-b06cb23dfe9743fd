from dataclasses import dataclass
from fractions import Fraction

from batches.roster import (
    Roster, canonical_document, load_document, require_fields, roster_from_record,
    roster_record, validate_roster,
)
from batches.units import decode_fraction, encode_fraction, require_identifier
from training.strategies import require_strategy


@dataclass(frozen=True, slots=True)
class ModelReference:
    model_id: str
    truth_id: str
    strategy: str
    parameter: Fraction


@dataclass(frozen=True, slots=True)
class PredictionRow:
    piece_id: str
    first: Fraction
    second: Fraction


@dataclass(frozen=True, slots=True)
class ForecastPair:
    package_id: str
    roster: Roster
    first_model: ModelReference
    second_model: ModelReference
    rows: tuple[PredictionRow, ...]


def _validate_model(reference):
    if not isinstance(reference, ModelReference):
        raise ValueError('expected fixed model provenance')
    require_identifier(reference.model_id, 'model ID')
    require_identifier(reference.truth_id, 'training truth ID')
    require_strategy(reference.strategy)
    if not isinstance(reference.parameter, Fraction) or reference.parameter < 0:
        raise ValueError('model parameter must be a nonnegative fraction')


def validate_forecast(package):
    if not isinstance(package, ForecastPair):
        raise ValueError('expected a paired forecast package')
    require_identifier(package.package_id, 'forecast package ID')
    validate_roster(package.roster)
    first, second = package.first_model, package.second_model
    _validate_model(first)
    _validate_model(second)
    if first.model_id == second.model_id and first != second:
        raise ValueError('one model ID cannot identify two versions')
    if not isinstance(package.rows, tuple) or len(package.rows) != len(package.roster.pieces):
        raise ValueError('forecast must cover the frozen roster')
    for piece, row in zip(package.roster.pieces, package.rows, strict=True):
        if not isinstance(row, PredictionRow) or row.piece_id != piece:
            raise ValueError('forecast rows must match the frozen piece order')
        if not isinstance(row.first, Fraction) or not isinstance(row.second, Fraction):
            raise ValueError('predictions must be exact fractions')
        if (row.first, row.second) != (first.parameter, second.parameter):
            raise ValueError('forecast row differs from its fixed model parameters')
    return package


def _model_record(reference):
    return {
        'id': reference.model_id, 'truth': reference.truth_id, 'strategy': reference.strategy,
        'parameter': encode_fraction(reference.parameter),
    }


def _model_from_record(record):
    require_fields(record, 'id', 'truth', 'strategy', 'parameter')
    return ModelReference(record['id'], record['truth'], record['strategy'], decode_fraction(record['parameter']))


def encode_forecast(package):
    validate_forecast(package)
    return canonical_document({
        'kind': 'forecast-pair/v1',
        'package_id': package.package_id,
        'roster': roster_record(package.roster),
        'models': [_model_record(package.first_model), _model_record(package.second_model)],
        'rows': [
            {'piece': row.piece_id, 'first': encode_fraction(row.first), 'second': encode_fraction(row.second)}
            for row in package.rows
        ],
    })


def decode_forecast(body):
    document = load_document(body)
    require_fields(document, 'kind', 'package_id', 'roster', 'models', 'rows')
    if document['kind'] != 'forecast-pair/v1' or not isinstance(document['rows'], list):
        raise ValueError('invalid forecast kind or rows')
    models = document['models']
    if not isinstance(models, list) or len(models) != 2:
        raise ValueError('forecast requires exactly two ordered model slots')
    rows = []
    for row in document['rows']:
        require_fields(row, 'piece', 'first', 'second')
        rows.append(PredictionRow(row['piece'], decode_fraction(row['first']), decode_fraction(row['second'])))
    return validate_forecast(ForecastPair(
        document['package_id'], roster_from_record(document['roster']),
        _model_from_record(models[0]), _model_from_record(models[1]), tuple(rows),
    ))
