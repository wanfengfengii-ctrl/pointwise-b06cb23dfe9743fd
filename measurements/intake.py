from batches.freeze import read_frozen_roster
from batches.registry import RosterRegistry, write_transaction
from batches.units import parse_um, require_identifier
from measurements.ledger import MeasurementLedger


def submit(db, roster_id, piece_id, source, value):
    require_identifier(piece_id, 'piece ID')
    require_identifier(source, 'measurement source')
    reading = parse_um(value)
    if reading < 0:
        raise ValueError('measurement must be nonnegative')
    ledger = MeasurementLedger(db)
    with write_transaction(db):
        roster = read_frozen_roster(db, roster_id)
        if piece_id not in roster.pieces:
            raise ValueError('piece is outside the frozen roster')
        existing = ledger.find_source(source)
        if existing is not None:
            original = (existing.roster_id, existing.piece_id, existing.value, existing.previous_id)
            if original != (roster_id, piece_id, reading, None):
                raise ValueError('measurement source already identifies a different request')
            return existing
        if ledger.read_seal(roster_id) is not None:
            raise ValueError('truth for this roster is already sealed')
        return ledger.save_initial(roster_id, piece_id, source, reading)


def submit_online(db, batch_id, piece_id, source, value):
    """Accept or re-claim the piece's first formal receipt for the online shift."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    require_identifier(source, 'measurement source')
    reading = parse_um(value)
    if reading < 0:
        raise ValueError('measurement must be nonnegative')
    ledger = MeasurementLedger(db)
    with write_transaction(db):
        roster = RosterRegistry(db).find_by_batch(batch_id)
        if roster is None:
            raise KeyError(batch_id)
        if piece_id not in roster.pieces:
            raise KeyError(piece_id)
        existing = ledger.find_source(source)
        if existing is not None:
            original = (existing.roster_id, existing.piece_id, existing.value, existing.previous_id)
            if original != (roster.roster_id, piece_id, reading, None):
                raise ValueError('measurement source already identifies a different request')
            return existing
        first = ledger.first_receipt(roster.roster_id, piece_id)
        if first is not None:
            if first.value != reading:
                raise ValueError('piece already has a different first measurement')
            return first
        return ledger.save_initial(roster.roster_id, piece_id, source, reading)
