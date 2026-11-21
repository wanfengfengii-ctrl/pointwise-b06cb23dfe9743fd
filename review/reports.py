from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from batches.registry import write_transaction
from batches.units import decode_fraction, require_identifier
from measurements.exchange import decode_truth, validate_truth
from measurements.ledger import MeasurementLedger
from measurements.seal import read_sealed_truth
from prediction.online import (
    decode_online_commitment, decode_online_prediction, require_online_roster_piece,
)
from review.admission import read_admitted_forecast
from review.pairing import PairedPiece, pair_for_review
from review.scoring import PieceScore, score_pieces
from review.store import ReviewStore


@dataclass(frozen=True, slots=True)
class ReviewReport:
    report_id: str
    admission_id: str
    package_id: str
    truth_id: str
    roster_id: str
    mean_delta: Fraction
    pieces: tuple[PieceScore, ...]


def report(db, admission_id, truth):
    submitted_truth = decode_truth(truth) if isinstance(truth, str) else validate_truth(truth)
    store = ReviewStore(db)
    with write_transaction(db):
        forecast = read_admitted_forecast(db, admission_id)
        try:
            actual_truth = read_sealed_truth(db, submitted_truth.truth_id)
        except KeyError as exc:
            raise ValueError('truth package is not a local issued seal') from exc
        if actual_truth != submitted_truth:
            raise ValueError('truth body differs from the local issued seal')
        paired = pair_for_review(forecast, actual_truth)
        existing = store.find_report_for_parents(admission_id, actual_truth.truth_id)
        if existing is not None:
            return read(db, existing)
        summary = score_pieces(paired)
        report_id = f'report-{uuid4().hex}'
        roster_id = actual_truth.roster.roster_id
        store.write_report(report_id, admission_id, forecast.package_id, actual_truth.truth_id, roster_id, summary)
        return ReviewReport(
            report_id, admission_id, forecast.package_id, actual_truth.truth_id, roster_id,
            summary.mean_delta, summary.pieces,
        )


def read(db, report_id):
    header, rows = ReviewStore(db).read_report(report_id)
    admission_id, package_id, truth_id, roster_id, mean_delta = header
    pieces = tuple(
        PieceScore(piece, decode_fraction(first), decode_fraction(second), decode_fraction(delta))
        for piece, first, second, delta in rows
    )
    return ReviewReport(report_id, admission_id, package_id, truth_id, roster_id,
                        decode_fraction(mean_delta), pieces)


def _online_report_dict(row):
    (report_id, batch_id, roster_id, piece_id, receipt_id, commitment_id,
     cutoff, first, second, actual, delta) = row
    return {
        'report_id': report_id,
        'batch_id': batch_id,
        'roster_id': roster_id,
        'piece_id': piece_id,
        'receipt_id': receipt_id,
        'commitment_id': commitment_id,
        'cutoff': cutoff,
        'first': decode_fraction(first),
        'second': decode_fraction(second),
        'actual': decode_fraction(actual),
        'delta': decode_fraction(delta),
    }


def report_online(db, batch_id, piece_id):
    """Sign the piece's online report once commitment, prediction and first receipt are in."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    store = ReviewStore(db)
    with write_transaction(db):
        roster = require_online_roster_piece(db, batch_id, piece_id)
        existing = store.find_online_report(roster.roster_id, piece_id)
        if existing is not None:
            return _online_report_dict(existing)
        commitment_body = store.find_online_commitment(roster.roster_id, piece_id)
        prediction_body = store.find_online_prediction(roster.roster_id, piece_id)
        receipt = MeasurementLedger(db).first_receipt(roster.roster_id, piece_id)
        if commitment_body is None or prediction_body is None or receipt is None:
            return None
        commitment = decode_online_commitment(commitment_body)
        prediction = decode_online_prediction(prediction_body)
        score = score_pieces(
            (PairedPiece(piece_id, prediction.first, prediction.second, receipt.value),)
        ).pieces[0]
        report_id = f'online-report-{uuid4().hex}'
        store.write_online_report(
            report_id, roster.roster_id, piece_id, receipt.receipt_id, commitment.commitment_id,
            commitment.cutoff, prediction.first, prediction.second, receipt.value, score.delta,
        )
        return read_online_report(db, report_id)


def read_online_report(db, report_id):
    return _online_report_dict(ReviewStore(db).read_online_report(report_id))
