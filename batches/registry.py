from contextlib import contextmanager

from batches.roster import decode_roster, encode_roster
from batches.units import require_identifier


@contextmanager
def write_transaction(db):
    """Serialize a station's read/write decisions and compose local writes."""
    if db.in_transaction:
        db.execute('SAVEPOINT station_write')
        try:
            yield
            db.execute('RELEASE station_write')
        except BaseException:
            db.execute('ROLLBACK TO station_write')
            db.execute('RELEASE station_write')
            raise
    else:
        db.execute('BEGIN IMMEDIATE')
        try:
            yield
            db.commit()
        except BaseException:
            db.rollback()
            raise


def initialize_rosters(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS rosters (
            roster_id TEXT PRIMARY KEY NOT NULL,
            batch_id TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL
        )
    ''')


class RosterRegistry:
    def __init__(self, db):
        self.db = db

    def find_by_batch(self, batch_id):
        require_identifier(batch_id, 'batch ID')
        row = self.db.execute(
            'SELECT body FROM rosters WHERE batch_id = ?', (batch_id,)
        ).fetchone()
        return None if row is None else decode_roster(row[0])

    def save_snapshot(self, roster):
        body = encode_roster(roster)
        with write_transaction(self.db):
            row = self.db.execute('''
                SELECT body FROM rosters WHERE roster_id = ? OR batch_id = ?
            ''', (roster.roster_id, roster.batch_id)).fetchall()
            if row:
                if len(row) != 1 or decode_roster(row[0][0]) != roster:
                    raise ValueError('conflicting frozen roster binding')
                return decode_roster(row[0][0])
            self.db.execute('''
                INSERT INTO rosters (roster_id, batch_id, body) VALUES (?, ?, ?)
            ''', (roster.roster_id, roster.batch_id, body))
        return roster

    def read_snapshot(self, roster_id):
        require_identifier(roster_id, 'roster ID')
        row = self.db.execute(
            'SELECT body FROM rosters WHERE roster_id = ?', (roster_id,)
        ).fetchone()
        if row is None:
            raise KeyError(roster_id)
        return decode_roster(row[0])
