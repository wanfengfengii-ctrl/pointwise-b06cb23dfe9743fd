from dataclasses import dataclass
from fractions import Fraction

from batches.registry import write_transaction
from batches.units import decode_fraction, encode_fraction, require_identifier
from training.strategies import require_strategy


@dataclass(frozen=True, slots=True)
class ModelVersion:
    model_id: str
    truth_id: str
    strategy: str
    parameter: Fraction


def initialize_models(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS models (
            model_id TEXT PRIMARY KEY NOT NULL,
            truth_id TEXT NOT NULL REFERENCES training_truths(truth_id),
            strategy TEXT NOT NULL,
            parameter TEXT NOT NULL
        )
    ''')


def read_model(db, model_id):
    require_identifier(model_id, 'model ID')
    row = db.execute('''
        SELECT truth_id, strategy, parameter FROM models WHERE model_id = ?
    ''', (model_id,)).fetchone()
    if row is None:
        raise KeyError(model_id)
    truth_id, strategy, parameter = row
    return ModelVersion(model_id, truth_id, strategy, decode_fraction(parameter))


def publish_model(db, model):
    if not isinstance(model, ModelVersion):
        raise ValueError('expected a model version')
    require_identifier(model.model_id, 'model ID')
    require_identifier(model.truth_id, 'training truth ID')
    require_strategy(model.strategy)
    if not isinstance(model.parameter, Fraction) or model.parameter < 0:
        raise ValueError('model parameter must be a nonnegative fraction')
    parameter = encode_fraction(model.parameter)
    with write_transaction(db):
        db.execute('''
            INSERT INTO models (model_id, truth_id, strategy, parameter) VALUES (?, ?, ?, ?)
            ON CONFLICT (model_id) DO NOTHING
        ''', (model.model_id, model.truth_id, model.strategy, parameter))
        registered = read_model(db, model.model_id)
        if registered != model:
            raise ValueError('model ID is already bound to a different version')
        return registered
