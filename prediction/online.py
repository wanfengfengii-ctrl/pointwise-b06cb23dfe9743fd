"""Versioned exchange bodies and commitment storage for the online backtest."""
from dataclasses import dataclass
from fractions import Fraction

from batches.registry import RosterRegistry
from batches.roster import (
    Roster, canonical_document, load_document, require_fields, roster_from_record,
    roster_record, validate_roster,
)
from batches.units import decode_fraction, encode_fraction, require_identifier

COMMITMENT_KIND = 'online-commitment/v1'
PREDICTION_KIND = 'online-prediction/v1'
OBSERVATION_KIND = 'online-observation/v1'


@dataclass(frozen=True, slots=True)
class OnlineCommitment:
    commitment_id: str
    roster: Roster
    piece_id: str
    cutoff: int


@dataclass(frozen=True, slots=True)
class OnlinePrediction:
    commitment_id: str
    roster: Roster
    piece_id: str
    cutoff: int
    first: Fraction
    second: Fraction


@dataclass(frozen=True, slots=True)
class OnlineObservation:
    commitment_id: str
    roster: Roster
    piece_id: str
    receipt_id: str
    source: str
    actual: Fraction


def _require_cutoff(cutoff):
    if type(cutoff) is not int or cutoff < 0:
        raise ValueError('expected a nonnegative integer cutoff')
    return cutoff


def _require_reading(value, field):
    if not isinstance(value, Fraction) or value < 0:
        raise ValueError(f'expected a nonnegative fraction for {field}')
    return value


def _require_binding(commitment_id, roster, piece_id):
    require_identifier(commitment_id, 'commitment ID')
    validate_roster(roster)
    require_identifier(piece_id, 'piece ID')
    if piece_id not in roster.pieces:
        raise ValueError('piece is outside the frozen roster')


def validate_commitment(commitment):
    if not isinstance(commitment, OnlineCommitment):
        raise ValueError('expected an online commitment')
    _require_binding(commitment.commitment_id, commitment.roster, commitment.piece_id)
    _require_cutoff(commitment.cutoff)
    return commitment


def validate_prediction(prediction):
    if not isinstance(prediction, OnlinePrediction):
        raise ValueError('expected an online prediction')
    _require_binding(prediction.commitment_id, prediction.roster, prediction.piece_id)
    _require_cutoff(prediction.cutoff)
    _require_reading(prediction.first, 'first prediction')
    _require_reading(prediction.second, 'second prediction')
    return prediction


def validate_observation(observation):
    if not isinstance(observation, OnlineObservation):
        raise ValueError('expected an online observation')
    _require_binding(observation.commitment_id, observation.roster, observation.piece_id)
    require_identifier(observation.receipt_id, 'measurement receipt ID')
    require_identifier(observation.source, 'measurement source')
    _require_reading(observation.actual, 'actual reading')
    return observation


def encode_online_commitment(commitment):
    validate_commitment(commitment)
    return canonical_document({
        'kind': COMMITMENT_KIND,
        'commitment_id': commitment.commitment_id,
        'roster': roster_record(commitment.roster),
        'piece_id': commitment.piece_id,
        'cutoff': commitment.cutoff,
    })


def decode_online_commitment(body):
    document = load_document(body)
    require_fields(document, 'kind', 'commitment_id', 'roster', 'piece_id', 'cutoff')
    if document['kind'] != COMMITMENT_KIND:
        raise ValueError('invalid online commitment kind')
    return validate_commitment(OnlineCommitment(
        document['commitment_id'], roster_from_record(document['roster']),
        document['piece_id'], document['cutoff'],
    ))


def encode_online_prediction(prediction):
    validate_prediction(prediction)
    return canonical_document({
        'kind': PREDICTION_KIND,
        'commitment_id': prediction.commitment_id,
        'roster': roster_record(prediction.roster),
        'piece_id': prediction.piece_id,
        'cutoff': prediction.cutoff,
        'first': encode_fraction(prediction.first),
        'second': encode_fraction(prediction.second),
    })


def decode_online_prediction(body):
    document = load_document(body)
    require_fields(document, 'kind', 'commitment_id', 'roster', 'piece_id', 'cutoff', 'first', 'second')
    if document['kind'] != PREDICTION_KIND:
        raise ValueError('invalid online prediction kind')
    return validate_prediction(OnlinePrediction(
        document['commitment_id'], roster_from_record(document['roster']),
        document['piece_id'], document['cutoff'],
        decode_fraction(document['first']), decode_fraction(document['second']),
    ))


def encode_online_observation(observation):
    validate_observation(observation)
    return canonical_document({
        'kind': OBSERVATION_KIND,
        'commitment_id': observation.commitment_id,
        'roster': roster_record(observation.roster),
        'piece_id': observation.piece_id,
        'receipt_id': observation.receipt_id,
        'source': observation.source,
        'actual': encode_fraction(observation.actual),
    })


def decode_online_observation(body):
    document = load_document(body)
    require_fields(document, 'kind', 'commitment_id', 'roster', 'piece_id', 'receipt_id', 'source', 'actual')
    if document['kind'] != OBSERVATION_KIND:
        raise ValueError('invalid online observation kind')
    return validate_observation(OnlineObservation(
        document['commitment_id'], roster_from_record(document['roster']),
        document['piece_id'], document['receipt_id'], document['source'],
        decode_fraction(document['actual']),
    ))


def require_online_roster_piece(db, batch_id, piece_id):
    """Locate the frozen roster and piece for online entries, or raise KeyError."""
    roster = RosterRegistry(db).find_by_batch(batch_id)
    if roster is None:
        raise KeyError(batch_id)
    if piece_id not in roster.pieces:
        raise KeyError(piece_id)
    return roster


def initialize_online_commitments(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS online_commitments (
            commitment_id TEXT PRIMARY KEY NOT NULL,
            roster_id TEXT NOT NULL REFERENCES rosters(roster_id),
            piece_id TEXT NOT NULL,
            cutoff INTEGER NOT NULL,
            first TEXT NOT NULL,
            second TEXT NOT NULL,
            UNIQUE (roster_id, piece_id)
        )
    ''')


def find_online_commitment(db, roster_id, piece_id):
    """Return (commitment_id, cutoff, first, second) for the piece, or None."""
    row = db.execute('''
        SELECT commitment_id, cutoff, first, second FROM online_commitments
        WHERE roster_id = ? AND piece_id = ?
    ''', (roster_id, piece_id)).fetchone()
    if row is None:
        return None
    commitment_id, cutoff, first, second = row
    return commitment_id, cutoff, decode_fraction(first), decode_fraction(second)


def save_online_commitment(db, commitment_id, roster_id, piece_id, cutoff, first, second):
    db.execute('''
        INSERT INTO online_commitments (commitment_id, roster_id, piece_id, cutoff, first, second)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (commitment_id, roster_id, piece_id, cutoff,
          encode_fraction(first), encode_fraction(second)))


def read_online_commitment_binding(db, commitment_id):
    """Return the (roster_id, piece_id) a commitment binds, or None."""
    require_identifier(commitment_id, 'commitment ID')
    row = db.execute('''
        SELECT roster_id, piece_id FROM online_commitments WHERE commitment_id = ?
    ''', (commitment_id,)).fetchone()
    return None if row is None else (row[0], row[1])
