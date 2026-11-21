from batches.registry import RosterRegistry, write_transaction
from batches.units import require_identifier
from measurements.exchange import decode_truth, encode_truth, validate_truth


def initialize_training_inputs(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS training_truths (
            truth_id TEXT PRIMARY KEY NOT NULL,
            roster_id TEXT NOT NULL UNIQUE REFERENCES rosters(roster_id),
            body TEXT NOT NULL
        )
    ''')


def admit_training_truth(db, truth):
    accepted = decode_truth(truth) if isinstance(truth, str) else validate_truth(truth)
    body = encode_truth(accepted)
    with write_transaction(db):
        RosterRegistry(db).save_snapshot(accepted.roster)
        matches = db.execute('''
            SELECT body FROM training_truths WHERE truth_id = ? OR roster_id = ?
        ''', (accepted.truth_id, accepted.roster.roster_id)).fetchall()
        if matches:
            existing = decode_truth(matches[0][0])
            if len(matches) != 1 or existing != accepted:
                raise ValueError('conflicting frozen training truth')
            return existing
        db.execute('''
            INSERT INTO training_truths (truth_id, roster_id, body) VALUES (?, ?, ?)
        ''', (accepted.truth_id, accepted.roster.roster_id, body))
        return accepted


def read_training_truth(db, truth_id):
    require_identifier(truth_id, 'training truth ID')
    row = db.execute('SELECT body FROM training_truths WHERE truth_id = ?', (truth_id,)).fetchone()
    if row is None:
        raise KeyError(truth_id)
    return decode_truth(row[0])
