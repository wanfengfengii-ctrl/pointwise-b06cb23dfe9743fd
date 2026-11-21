from uuid import uuid4

from batches.freeze import read_frozen_roster
from batches.registry import write_transaction
from batches.roster import Roster, validate_roster
from batches.units import require_identifier
from prediction.apply import apply_models
from prediction.receipts import find_forecast_by_request, issue_forecast
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
