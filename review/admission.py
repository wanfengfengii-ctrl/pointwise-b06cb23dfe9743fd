from uuid import uuid4

from batches.registry import write_transaction
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
