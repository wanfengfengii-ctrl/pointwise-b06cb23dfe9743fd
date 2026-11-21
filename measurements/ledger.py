from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from batches.units import decode_fraction, encode_fraction, require_identifier


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: str
    roster_id: str
    piece_id: str
    source: str
    value: Fraction
    previous_id: str | None = None


_RECEIPT_COLUMNS = 'r.receipt_id, r.roster_id, r.piece_id, r.source, r.value, r.previous_id'


def initialize_measurements(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS measurement_receipts (
            ordinal INTEGER PRIMARY KEY,
            receipt_id TEXT NOT NULL UNIQUE,
            roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
            piece_id TEXT NOT NULL,
            source TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            previous_id TEXT REFERENCES measurement_receipts(receipt_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS current_measurements (
            roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
            piece_id TEXT NOT NULL,
            receipt_id TEXT NOT NULL UNIQUE REFERENCES measurement_receipts(receipt_id),
            PRIMARY KEY (roster_id, piece_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS truth_seals (
            truth_id TEXT PRIMARY KEY NOT NULL,
            roster_id TEXT NOT NULL UNIQUE REFERENCES rosters(roster_id),
            body TEXT NOT NULL
        )
    ''')


def _receipt(row):
    receipt_id, roster_id, piece_id, source, value, previous_id = row
    return Receipt(receipt_id, roster_id, piece_id, source, decode_fraction(value), previous_id)


class MeasurementLedger:
    """Measurement storage. The submit, correct and seal operations own writes."""

    def __init__(self, db):
        self.db = db

    def find_source(self, source):
        require_identifier(source, 'measurement source')
        row = self.db.execute(f'''
            SELECT {_RECEIPT_COLUMNS} FROM measurement_receipts r WHERE r.source = ?
        ''', (source,)).fetchone()
        return None if row is None else _receipt(row)

    def get_receipt(self, receipt_id):
        require_identifier(receipt_id, 'measurement receipt ID')
        row = self.db.execute(f'''
            SELECT {_RECEIPT_COLUMNS} FROM measurement_receipts r WHERE r.receipt_id = ?
        ''', (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return _receipt(row)

    def current_receipts(self, roster_id):
        rows = self.db.execute(f'''
            SELECT {_RECEIPT_COLUMNS}
            FROM current_measurements AS current
            JOIN measurement_receipts r ON r.receipt_id = current.receipt_id
            WHERE current.roster_id = ?
            ORDER BY r.ordinal
        ''', (roster_id,))
        return {row[2]: _receipt(row) for row in rows}

    def first_receipt(self, roster_id, piece_id):
        """The piece's first formal receipt, before any later corrections."""
        row = self.db.execute(f'''
            SELECT {_RECEIPT_COLUMNS} FROM measurement_receipts r
            WHERE r.roster_id = ? AND r.piece_id = ? AND r.previous_id IS NULL
        ''', (roster_id, piece_id)).fetchone()
        return None if row is None else _receipt(row)

    def _append(self, roster_id, piece_id, source, value, previous_id=None):
        ordinal = self.db.execute(
            'SELECT COALESCE(MAX(ordinal), 0) + 1 FROM measurement_receipts'
        ).fetchone()[0]
        receipt_id = f'measurement-{ordinal:012d}-{uuid4().hex}'
        self.db.execute('''
            INSERT INTO measurement_receipts
                (ordinal, receipt_id, roster_id, piece_id, source, value, previous_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ordinal, receipt_id, roster_id, piece_id, source, encode_fraction(value), previous_id))
        return Receipt(receipt_id, roster_id, piece_id, source, value, previous_id)

    def save_initial(self, roster_id, piece_id, source, value):
        existing = self.db.execute('''
            SELECT receipt_id FROM current_measurements WHERE roster_id = ? AND piece_id = ?
        ''', (roster_id, piece_id)).fetchone()
        if existing is not None:
            raise ValueError('piece already has a current receipt')
        receipt = self._append(roster_id, piece_id, source, value)
        self.db.execute('''
            INSERT INTO current_measurements (roster_id, piece_id, receipt_id) VALUES (?, ?, ?)
        ''', (roster_id, piece_id, receipt.receipt_id))
        return receipt

    def replace_current(self, before, source, value):
        receipt = self._append(before.roster_id, before.piece_id, source, value, before.receipt_id)
        updated = self.db.execute('''
            UPDATE current_measurements SET receipt_id = ?
            WHERE roster_id = ? AND piece_id = ? AND receipt_id = ?
        ''', (receipt.receipt_id, before.roster_id, before.piece_id, before.receipt_id))
        if updated.rowcount != 1:
            raise ValueError('previous receipt is no longer current')
        return receipt

    def read_seal(self, roster_id):
        row = self.db.execute(
            'SELECT body FROM truth_seals WHERE roster_id = ?', (roster_id,)
        ).fetchone()
        return None if row is None else row[0]

    def save_seal(self, roster_id, truth_id, body):
        self.db.execute('''
            INSERT INTO truth_seals (roster_id, truth_id, body) VALUES (?, ?, ?)
        ''', (roster_id, truth_id, body))
