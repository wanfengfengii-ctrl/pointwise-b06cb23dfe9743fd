from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from batches.registry import write_transaction
from batches.units import decode_fraction
from measurements.exchange import decode_truth, validate_truth
from measurements.seal import read_sealed_truth
from review.admission import read_admitted_forecast
from review.pairing import pair_for_review
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
