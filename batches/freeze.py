from dataclasses import replace
from uuid import uuid4

from batches.gauges import read_gauge
from batches.registry import RosterRegistry, write_transaction
from batches.roster import Roster, require_piece_order, validate_roster


def freeze_roster(db, batch_id, gauge, nominal_um, pieces):
    proposed = validate_roster(Roster(
        f'roster-{uuid4().hex}', batch_id, gauge, nominal_um, require_piece_order(pieces)
    ))
    registry = RosterRegistry(db)
    with write_transaction(db):
        if read_gauge(db, gauge.gauge_id) != gauge:
            raise ValueError('gauge does not match its registration')
        existing = registry.find_by_batch(batch_id)
        if existing is not None:
            if replace(proposed, roster_id=existing.roster_id) != existing:
                raise ValueError('batch already has a different frozen roster')
            return existing
        return registry.save_snapshot(proposed)


def read_frozen_roster(db, roster_id):
    return RosterRegistry(db).read_snapshot(roster_id)
