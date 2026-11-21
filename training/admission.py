from batches.registry import RosterRegistry, write_transaction
from batches.units import decode_fraction, encode_fraction, require_identifier
from measurements.exchange import decode_truth, encode_truth, validate_truth
from prediction.online import (
    decode_online_observation, encode_online_observation, read_online_commitment_binding,
)


def initialize_training_inputs(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS training_truths (
            truth_id TEXT PRIMARY KEY NOT NULL,
            roster_id TEXT NOT NULL UNIQUE REFERENCES rosters(roster_id),
            body TEXT NOT NULL
        )
    ''')


def initialize_online_training(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS online_training (
            roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
            seq INTEGER NOT NULL,
            commitment_id TEXT NOT NULL REFERENCES online_commitments(commitment_id),
            piece_id TEXT NOT NULL,
            receipt_id TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            body TEXT NOT NULL,
            PRIMARY KEY (roster_id, seq),
            UNIQUE (roster_id, piece_id)
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


def count_online_training(db, roster_id):
    require_identifier(roster_id, 'roster ID')
    return db.execute(
        'SELECT COUNT(*) FROM online_training WHERE roster_id = ?', (roster_id,)
    ).fetchone()[0]


def online_training_values(db, roster_id, cutoff):
    """Exact admitted values of the first `cutoff` online rows in admission order."""
    require_identifier(roster_id, 'roster ID')
    if type(cutoff) is not int or cutoff < 0:
        raise ValueError('expected a nonnegative integer cutoff')
    rows = db.execute('''
        SELECT value FROM online_training WHERE roster_id = ? AND seq <= ? ORDER BY seq
    ''', (roster_id, cutoff)).fetchall()
    return [decode_fraction(row[0]) for row in rows]


def online_training_size(db, batch_id):
    require_identifier(batch_id, 'batch ID')
    roster = RosterRegistry(db).find_by_batch(batch_id)
    if roster is None:
        raise KeyError(batch_id)
    return count_online_training(db, roster.roster_id)


def admit_online_observation(db, body):
    observation = decode_online_observation(body)
    canonical = encode_online_observation(observation)
    with write_transaction(db):
        binding = read_online_commitment_binding(db, observation.commitment_id)
        if binding is None:
            raise ValueError('observation references an unknown commitment')
        roster_id, piece_id = binding
        roster = RosterRegistry(db).read_snapshot(roster_id)
        if observation.piece_id != piece_id or observation.roster != roster:
            raise ValueError('observation does not match its committed binding')
        existing = db.execute('''
            SELECT seq, body FROM online_training WHERE roster_id = ? AND piece_id = ?
        ''', (roster_id, piece_id)).fetchone()
        if existing is not None:
            if existing[1] != canonical:
                raise ValueError('piece already supplied a different observation')
            return existing[0]
        conflict = db.execute(
            'SELECT 1 FROM online_training WHERE receipt_id = ?', (observation.receipt_id,)
        ).fetchone()
        if conflict is not None:
            raise ValueError('receipt is already attributed to another piece')
        seq = count_online_training(db, roster_id) + 1
        db.execute('''
            INSERT INTO online_training (roster_id, seq, commitment_id, piece_id, receipt_id, value, body)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (roster_id, seq, observation.commitment_id, piece_id, observation.receipt_id,
              encode_fraction(observation.actual), canonical))
        return seq
