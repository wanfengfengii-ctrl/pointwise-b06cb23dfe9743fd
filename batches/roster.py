import json
from dataclasses import dataclass
from fractions import Fraction

from batches.gauges import Gauge, validate_gauge
from batches.units import decode_fraction, encode_fraction, require_identifier


@dataclass(frozen=True, slots=True)
class Roster:
    roster_id: str
    batch_id: str
    gauge: Gauge
    nominal_um: Fraction
    pieces: tuple[str, ...]


def require_piece_order(pieces):
    if not isinstance(pieces, (tuple, list)) or not pieces:
        raise ValueError('expected a nonempty ordered list of pieces')
    for piece in pieces:
        require_identifier(piece, 'piece ID')
    if len(set(pieces)) != len(pieces):
        raise ValueError('duplicate piece in the roster')
    return tuple(pieces)


def validate_roster(roster):
    if not isinstance(roster, Roster):
        raise ValueError('expected a frozen roster')
    require_identifier(roster.roster_id, 'roster ID')
    require_identifier(roster.batch_id, 'batch ID')
    validate_gauge(roster.gauge)
    if not isinstance(roster.nominal_um, Fraction) or roster.nominal_um <= 0:
        raise ValueError('nominal thickness must be positive')
    if not isinstance(roster.pieces, tuple):
        raise ValueError('frozen piece order must be a tuple')
    require_piece_order(roster.pieces)
    return roster


def _unique_object(pairs):
    result = {}
    for field, value in pairs:
        if field in result:
            raise ValueError(f'duplicate field {field}')
        result[field] = value
    return result


def load_document(body):
    if not isinstance(body, str):
        raise ValueError('exchange body must be JSON text')
    try:
        return json.loads(body, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid exchange JSON') from exc


def canonical_document(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require_fields(record, *fields):
    if not isinstance(record, dict) or record.keys() != set(fields):
        raise ValueError('unexpected exchange fields')


def roster_record(roster):
    validate_roster(roster)
    return {
        'kind': 'roster/v1',
        'roster_id': roster.roster_id,
        'batch_id': roster.batch_id,
        'gauge': {'id': roster.gauge.gauge_id, 'provenance': roster.gauge.provenance},
        'nominal_um': encode_fraction(roster.nominal_um),
        'pieces': list(roster.pieces),
    }


def roster_from_record(record):
    require_fields(record, 'kind', 'roster_id', 'batch_id', 'gauge', 'nominal_um', 'pieces')
    if record['kind'] != 'roster/v1' or not isinstance(record['pieces'], list):
        raise ValueError('invalid roster kind or piece order')
    gauge = record['gauge']
    require_fields(gauge, 'id', 'provenance')
    return validate_roster(Roster(
        record['roster_id'],
        record['batch_id'],
        Gauge(gauge['id'], gauge['provenance']),
        decode_fraction(record['nominal_um']),
        tuple(record['pieces']),
    ))


def encode_roster(roster):
    return canonical_document(roster_record(roster))


def decode_roster(body):
    return roster_from_record(load_document(body))
