from dataclasses import dataclass
from fractions import Fraction

from batches.roster import (
    Roster, canonical_document, load_document, require_fields, roster_from_record,
    roster_record, validate_roster,
)
from batches.units import decode_fraction, encode_fraction, require_identifier


@dataclass(frozen=True, slots=True)
class TruthRow:
    piece_id: str
    value: Fraction
    receipt_id: str
    source: str


@dataclass(frozen=True, slots=True)
class FrozenTruth:
    truth_id: str
    roster: Roster
    rows: tuple[TruthRow, ...]


def validate_truth(truth):
    if not isinstance(truth, FrozenTruth):
        raise ValueError('expected a frozen truth package')
    require_identifier(truth.truth_id, 'truth ID')
    validate_roster(truth.roster)
    if not isinstance(truth.rows, tuple) or len(truth.rows) != len(truth.roster.pieces):
        raise ValueError('truth must cover the full frozen roster')
    receipts = set()
    sources = set()
    for piece_id, row in zip(truth.roster.pieces, truth.rows, strict=True):
        if not isinstance(row, TruthRow) or row.piece_id != piece_id:
            raise ValueError('truth rows must match the frozen piece order')
        require_identifier(row.receipt_id, 'measurement receipt ID')
        require_identifier(row.source, 'measurement source')
        if row.receipt_id in receipts or row.source in sources:
            raise ValueError('repeated measurement provenance in truth package')
        if not isinstance(row.value, Fraction) or row.value < 0:
            raise ValueError('truth readings must be nonnegative fractions')
        receipts.add(row.receipt_id)
        sources.add(row.source)
    return truth


def encode_truth(truth):
    validate_truth(truth)
    return canonical_document({
        'kind': 'truth/v1',
        'truth_id': truth.truth_id,
        'roster': roster_record(truth.roster),
        'rows': [
            {'piece': row.piece_id, 'value': encode_fraction(row.value),
             'receipt': row.receipt_id, 'source': row.source}
            for row in truth.rows
        ],
    })


def decode_truth(body):
    document = load_document(body)
    require_fields(document, 'kind', 'truth_id', 'roster', 'rows')
    if document['kind'] != 'truth/v1' or not isinstance(document['rows'], list):
        raise ValueError('invalid truth kind or rows')
    rows = []
    for row in document['rows']:
        require_fields(row, 'piece', 'value', 'receipt', 'source')
        rows.append(TruthRow(row['piece'], decode_fraction(row['value']), row['receipt'], row['source']))
    return validate_truth(FrozenTruth(
        document['truth_id'], roster_from_record(document['roster']), tuple(rows)
    ))
