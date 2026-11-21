from fractions import Fraction
from uuid import uuid4

from batches.freeze import read_frozen_roster
from batches.registry import write_transaction
from batches.roster import Roster, validate_roster
from batches.units import require_identifier
from prediction.apply import apply_models
from prediction.online import (
    OnlineCommitment, OnlinePrediction, encode_online_commitment, encode_online_prediction,
    find_online_commitment, require_online_roster_piece, save_online_commitment,
)
from prediction.receipts import find_forecast_by_request, issue_forecast
from training.admission import count_online_training, online_training_values
from training.catalog import read_model


def forecast(db, target, first_model_id, second_model_id):
    require_identifier(first_model_id, 'first model ID')
    require_identifier(second_model_id, 'second model ID')
    snapshot = validate_roster(target) if isinstance(target, Roster) else None
    roster_id = target if snapshot is None else snapshot.roster_id
    with write_transaction(db):
        roster = read_frozen_roster(db, roster_id)
        if snapshot is not None and snapshot != roster:
            raise ValueError('target does not match the accepted frozen roster')
        first = read_model(db, first_model_id)
        second = read_model(db, second_model_id)
        existing = find_forecast_by_request(db, roster_id, first_model_id, second_model_id)
        if existing is not None:
            return existing
        package = apply_models(f'forecast-{uuid4().hex}', roster, first, second)
        return issue_forecast(db, package)


def begin_online(db, batch_id, piece_id):
    """Persist the piece's online commitment and return its exchange body."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    with write_transaction(db):
        roster = require_online_roster_piece(db, batch_id, piece_id)
        found = find_online_commitment(db, roster.roster_id, piece_id)
        if found is None:
            cutoff = count_online_training(db, roster.roster_id)
            values = online_training_values(db, roster.roster_id, cutoff)
            if values:
                first = values[-1]
                second = sum(values, Fraction(0)) / len(values)
            else:
                first = second = roster.nominal_um
            commitment_id = f'commitment-{uuid4().hex}'
            save_online_commitment(db, commitment_id, roster.roster_id, piece_id, cutoff, first, second)
        else:
            commitment_id, cutoff, first, second = found
        return encode_online_commitment(OnlineCommitment(commitment_id, roster, piece_id, cutoff))


def collect_online(db, batch_id, piece_id):
    """Return the persisted dual prediction body for an earlier commitment."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    roster = require_online_roster_piece(db, batch_id, piece_id)
    found = find_online_commitment(db, roster.roster_id, piece_id)
    if found is None:
        raise KeyError(piece_id)
    commitment_id, cutoff, first, second = found
    return encode_online_prediction(OnlinePrediction(commitment_id, roster, piece_id, cutoff, first, second))
