from dataclasses import dataclass

from batches.units import require_identifier


@dataclass(frozen=True, slots=True)
class Gauge:
    gauge_id: str
    provenance: str


def validate_gauge(gauge):
    if not isinstance(gauge, Gauge):
        raise ValueError('expected a gauge record')
    require_identifier(gauge.gauge_id, 'gauge ID')
    require_identifier(gauge.provenance, 'gauge provenance')
    return gauge


def initialize_gauges(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS gauges (
            gauge_id TEXT PRIMARY KEY NOT NULL,
            provenance TEXT NOT NULL
        )
    ''')


def read_gauge(db, gauge_id):
    require_identifier(gauge_id, 'gauge ID')
    row = db.execute(
        'SELECT provenance FROM gauges WHERE gauge_id = ?', (gauge_id,)
    ).fetchone()
    if row is None:
        raise KeyError(gauge_id)
    return Gauge(gauge_id, row[0])


def register_gauge(db, gauge_id, provenance):
    requested = validate_gauge(Gauge(gauge_id, provenance))
    db.execute('''
        INSERT INTO gauges (gauge_id, provenance) VALUES (?, ?)
        ON CONFLICT (gauge_id) DO NOTHING
    ''', (gauge_id, provenance))
    registered = read_gauge(db, gauge_id)
    if registered != requested:
        raise ValueError('gauge ID already has different provenance')
    return registered
