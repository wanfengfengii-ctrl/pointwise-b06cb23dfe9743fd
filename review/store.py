import sqlite3

from batches.gauges import initialize_gauges
from batches.registry import initialize_rosters, write_transaction
from batches.units import encode_fraction, require_identifier
from measurements.ledger import initialize_measurements


def open_review(path):
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        with write_transaction(db):
            initialize_gauges(db)
            initialize_rosters(db)
            initialize_measurements(db)
            db.execute('''
                CREATE TABLE IF NOT EXISTS forecast_admissions (
                    admission_id TEXT PRIMARY KEY NOT NULL,
                    package_id TEXT NOT NULL UNIQUE,
                    body TEXT NOT NULL
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS review_reports (
                    report_id TEXT PRIMARY KEY NOT NULL,
                    admission_id TEXT NOT NULL REFERENCES forecast_admissions(admission_id),
                    package_id TEXT NOT NULL,
                    truth_id TEXT NOT NULL REFERENCES truth_seals(truth_id),
                    roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
                    mean_delta TEXT NOT NULL,
                    UNIQUE (admission_id, truth_id)
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS report_pieces (
                    report_id TEXT NOT NULL REFERENCES review_reports(report_id),
                    position INTEGER NOT NULL,
                    piece_id TEXT NOT NULL,
                    first_squared TEXT NOT NULL,
                    second_squared TEXT NOT NULL,
                    delta TEXT NOT NULL,
                    PRIMARY KEY (report_id, position),
                    UNIQUE (report_id, piece_id)
                )
            ''')
    except BaseException:
        db.close()
        raise
    return db


class ReviewStore:
    """Persist review records under the admission or signing transaction."""

    def __init__(self, db):
        self.db = db

    def find_admission_by_package(self, package_id):
        require_identifier(package_id, 'forecast package ID')
        return self.db.execute('''
            SELECT admission_id, body FROM forecast_admissions WHERE package_id = ?
        ''', (package_id,)).fetchone()

    def write_admission(self, admission_id, package_id, body):
        self.db.execute('''
            INSERT INTO forecast_admissions (admission_id, package_id, body) VALUES (?, ?, ?)
        ''', (admission_id, package_id, body))

    def read_admission(self, admission_id):
        require_identifier(admission_id, 'forecast admission ID')
        row = self.db.execute('''
            SELECT body FROM forecast_admissions WHERE admission_id = ?
        ''', (admission_id,)).fetchone()
        if row is None:
            raise KeyError(admission_id)
        return row[0]

    def find_report_for_parents(self, admission_id, truth_id):
        row = self.db.execute('''
            SELECT report_id FROM review_reports WHERE admission_id = ? AND truth_id = ?
        ''', (admission_id, truth_id)).fetchone()
        return None if row is None else row[0]

    def write_report(self, report_id, admission_id, package_id, truth_id, roster_id, summary):
        self.db.execute('''
            INSERT INTO review_reports (report_id, admission_id, package_id, truth_id, roster_id, mean_delta)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (report_id, admission_id, package_id, truth_id, roster_id, encode_fraction(summary.mean_delta)))
        self.db.executemany('''
            INSERT INTO report_pieces (report_id, position, piece_id, first_squared, second_squared, delta)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            (report_id, position, row.piece_id, encode_fraction(row.first_squared),
             encode_fraction(row.second_squared), encode_fraction(row.delta))
            for position, row in enumerate(summary.pieces)
        ))

    def read_report(self, report_id):
        require_identifier(report_id, 'report ID')
        header = self.db.execute('''
            SELECT admission_id, package_id, truth_id, roster_id, mean_delta
            FROM review_reports WHERE report_id = ?
        ''', (report_id,)).fetchone()
        if header is None:
            raise KeyError(report_id)
        rows = self.db.execute('''
            SELECT piece_id, first_squared, second_squared, delta
            FROM report_pieces WHERE report_id = ? ORDER BY position
        ''', (report_id,)).fetchall()
        return header, rows
