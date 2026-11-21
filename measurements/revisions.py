from batches.registry import write_transaction
from batches.units import parse_um, require_identifier
from measurements.ledger import MeasurementLedger


def correct(db, receipt_id, value, source):
    require_identifier(source, 'correction source')
    reading = parse_um(value)
    if reading < 0:
        raise ValueError('measurement must be nonnegative')
    ledger = MeasurementLedger(db)
    with write_transaction(db):
        previous = ledger.get_receipt(receipt_id)
        if ledger.read_seal(previous.roster_id) is not None:
            raise ValueError('truth for this roster is already sealed')
        if ledger.find_source(source) is not None:
            raise ValueError('correction requires a new measurement source')
        return ledger.replace_current(previous, source, reading)
