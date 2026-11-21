from uuid import uuid4

from batches.registry import write_transaction
from batches.units import require_identifier
from measurements.ledger import MeasurementLedger
from prediction.online import (
    OnlineObservation, decode_online_commitment, decode_online_prediction,
    encode_online_commitment, encode_online_observation, encode_online_prediction,
    require_online_roster_piece,
)
from prediction.package import decode_forecast, encode_forecast, validate_forecast
from review.store import ReviewStore


def admit(db, package):
    incoming = decode_forecast(package) if isinstance(package, str) else validate_forecast(package)
    body = encode_forecast(incoming)
    store = ReviewStore(db)
    with write_transaction(db):
        match = store.find_admission_by_package(incoming.package_id)
        if match is not None:
            admission_id, original_body = match
            if decode_forecast(original_body) != incoming:
                raise ValueError('forecast package ID already has a different accepted body')
            return admission_id
        admission_id = f'admission-{uuid4().hex}'
        store.write_admission(admission_id, incoming.package_id, body)
        return admission_id


def read_admitted_forecast(db, admission_id):
    return decode_forecast(ReviewStore(db).read_admission(admission_id))


def accept_online_commitment(db, batch_id, piece_id, body):
    """Accept the piece's online commitment; re-accepting an equivalent body is a no-op."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    commitment = decode_online_commitment(body)
    store = ReviewStore(db)
    with write_transaction(db):
        roster = require_online_roster_piece(db, batch_id, piece_id)
        if commitment.piece_id != piece_id or commitment.roster != roster:
            raise ValueError('commitment does not match the local batch and piece')
        holder = store.find_online_commitment_piece(commitment.commitment_id)
        if holder is not None and holder != (roster.roster_id, piece_id):
            raise ValueError('commitment ID is already bound to another piece')
        existing = store.find_online_commitment(roster.roster_id, piece_id)
        if existing is not None:
            if decode_online_commitment(existing) != commitment:
                raise ValueError('piece already accepted a different commitment')
            return None
        store.write_online_commitment(roster.roster_id, piece_id, commitment.commitment_id,
                                      encode_online_commitment(commitment))
        return None


def accept_online_prediction(db, batch_id, piece_id, body):
    """Accept the dual prediction bound to the piece's accepted commitment."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    prediction = decode_online_prediction(body)
    store = ReviewStore(db)
    with write_transaction(db):
        roster = require_online_roster_piece(db, batch_id, piece_id)
        if prediction.piece_id != piece_id or prediction.roster != roster:
            raise ValueError('prediction does not match the local batch and piece')
        commitment_body = store.find_online_commitment(roster.roster_id, piece_id)
        if commitment_body is None:
            raise ValueError('piece has no accepted commitment')
        commitment = decode_online_commitment(commitment_body)
        if (prediction.commitment_id, prediction.cutoff) != (commitment.commitment_id, commitment.cutoff):
            raise ValueError('prediction does not match the accepted commitment')
        existing = store.find_online_prediction(roster.roster_id, piece_id)
        if existing is not None:
            if decode_online_prediction(existing) != prediction:
                raise ValueError('piece already accepted a different prediction')
            return None
        store.write_online_prediction(roster.roster_id, piece_id, encode_online_prediction(prediction))
        return None


def make_online_observation(db, batch_id, piece_id):
    """Build the piece's supply body once its commitment and first receipt are both in."""
    require_identifier(batch_id, 'batch ID')
    require_identifier(piece_id, 'piece ID')
    roster = require_online_roster_piece(db, batch_id, piece_id)
    commitment_body = ReviewStore(db).find_online_commitment(roster.roster_id, piece_id)
    if commitment_body is None:
        return None
    receipt = MeasurementLedger(db).first_receipt(roster.roster_id, piece_id)
    if receipt is None:
        return None
    commitment = decode_online_commitment(commitment_body)
    return encode_online_observation(OnlineObservation(
        commitment.commitment_id, roster, piece_id,
        receipt.receipt_id, receipt.source, receipt.value,
    ))
