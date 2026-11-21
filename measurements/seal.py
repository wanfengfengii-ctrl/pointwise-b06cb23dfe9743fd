from uuid import uuid4

from batches.freeze import read_frozen_roster
from batches.registry import write_transaction
from batches.units import require_identifier
from measurements.exchange import FrozenTruth, TruthRow, decode_truth, encode_truth
from measurements.ledger import MeasurementLedger


def seal(db, roster_id):
    ledger = MeasurementLedger(db)
    with write_transaction(db):
        roster = read_frozen_roster(db, roster_id)
        body = ledger.read_seal(roster_id)
        if body is not None:
            return decode_truth(body)
        current = ledger.current_receipts(roster_id)
        missing = [piece for piece in roster.pieces if piece not in current]
        if missing:
            raise ValueError(f'missing measurements for {missing!r}')
        rows = tuple(
            TruthRow(piece, receipt.value, receipt.receipt_id, receipt.source)
            for piece, receipt in ((piece, current[piece]) for piece in roster.pieces)
        )
        truth = FrozenTruth(f'truth-{uuid4().hex}', roster, rows)
        ledger.save_seal(roster_id, truth.truth_id, encode_truth(truth))
        return truth


def read_sealed_truth(db, truth_id):
    require_identifier(truth_id, 'truth ID')
    row = db.execute('SELECT body FROM truth_seals WHERE truth_id = ?', (truth_id,)).fetchone()
    if row is None:
        raise KeyError(truth_id)
    return decode_truth(row[0])
