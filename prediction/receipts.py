import sqlite3
from dataclasses import replace

from batches.registry import initialize_rosters, write_transaction
from batches.units import require_identifier
from prediction.package import decode_forecast, encode_forecast
from training.admission import initialize_training_inputs
from training.catalog import initialize_models


def open_prediction(path):
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        with write_transaction(db):
            initialize_rosters(db)
            initialize_training_inputs(db)
            initialize_models(db)
            db.execute('''
                CREATE TABLE IF NOT EXISTS issued_forecasts (
                    package_id TEXT PRIMARY KEY NOT NULL,
                    roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
                    first_model_id TEXT NOT NULL REFERENCES models(model_id),
                    second_model_id TEXT NOT NULL REFERENCES models(model_id),
                    body TEXT NOT NULL,
                    UNIQUE (roster_id, first_model_id, second_model_id)
                )
            ''')
    except BaseException:
        db.close()
        raise
    return db


def find_forecast_by_request(db, roster_id, first_model_id, second_model_id):
    require_identifier(roster_id, 'roster ID')
    require_identifier(first_model_id, 'first model ID')
    require_identifier(second_model_id, 'second model ID')
    row = db.execute('''
        SELECT body FROM issued_forecasts
        WHERE roster_id = ? AND first_model_id = ? AND second_model_id = ?
    ''', (roster_id, first_model_id, second_model_id)).fetchone()
    return None if row is None else decode_forecast(row[0])


def issue_forecast(db, package):
    body = encode_forecast(package)
    roster_id = package.roster.roster_id
    first = package.first_model.model_id
    second = package.second_model.model_id
    with write_transaction(db):
        existing = find_forecast_by_request(db, roster_id, first, second)
        if existing is not None:
            if existing != replace(package, package_id=existing.package_id):
                raise ValueError('forecast request already has a different body')
            return existing
        duplicate_id = db.execute(
            'SELECT 1 FROM issued_forecasts WHERE package_id = ?', (package.package_id,)
        ).fetchone()
        if duplicate_id is not None:
            raise ValueError('forecast package ID already exists')
        db.execute('''
            INSERT INTO issued_forecasts (package_id, roster_id, first_model_id, second_model_id, body)
            VALUES (?, ?, ?, ?, ?)
        ''', (package.package_id, roster_id, first, second, body))
        return package


def read_forecast(db, package_id):
    require_identifier(package_id, 'forecast package ID')
    row = db.execute('SELECT body FROM issued_forecasts WHERE package_id = ?', (package_id,)).fetchone()
    if row is None:
        raise KeyError(package_id)
    return decode_forecast(row[0])
