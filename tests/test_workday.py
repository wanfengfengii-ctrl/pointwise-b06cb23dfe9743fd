import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from batches.gauges import register_gauge
from batches.register import register
from batches.registry import RosterRegistry
from batches.units import encode_fraction
from measurements.exchange import encode_truth
from measurements.intake import submit
from measurements.revisions import correct
from measurements.seal import seal
from prediction.jobs import forecast
from prediction.package import encode_forecast
from prediction.receipts import open_prediction
from review.admission import admit, read_admitted_forecast
from review.reports import read, report
from review.store import open_review
from training.admission import read_training_truth
from training.fit import train
from training.strategies import LAST_PIECE, MEAN


_SAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'workday.json'


def _enter_batch(review, sample, name):
    batch = sample[name]
    roster = register(review, batch['batch_id'], sample['gauge_id'], sample['nominal_um'], sample['pieces'])
    receipts = tuple(
        submit(review, roster.roster_id, piece, f'{roster.batch_id}.{piece}', value)
        for piece, value in zip(roster.pieces, batch['values'], strict=True)
    )
    return roster, receipts


def _reported_scores(result):
    return {
        'scores': [[row.piece_id, encode_fraction(row.first_squared), encode_fraction(row.second_squared),
                    encode_fraction(row.delta)] for row in result.pieces],
        'mean_delta': encode_fraction(result.mean_delta),
    }


def run_workday(directory, sample):
    review_path = directory / 'review.sqlite3'
    prediction_path = directory / 'prediction.sqlite3'
    with closing(open_review(review_path)) as review:
        register_gauge(review, sample['gauge_id'], sample['gauge_provenance'])
        historical, receipts = _enter_batch(review, sample, 'history')
        corrected = correct(review, receipts[-1].receipt_id, sample['history']['corrected_last'], 'H.correction')
        truth = seal(review, historical.roster_id)
        target = register(review, sample['target']['batch_id'], sample['gauge_id'],
                          sample['nominal_um'], sample['pieces'])

    with closing(open_prediction(prediction_path)) as prediction:
        first = train(prediction, encode_truth(truth), sample['models'][0], LAST_PIECE)
        second = train(prediction, truth, sample['models'][1], MEAN)
        training_input = read_training_truth(prediction, first.truth_id)
        RosterRegistry(prediction).save_snapshot(target)
        package = forecast(prediction, target.roster_id, first.model_id, second.model_id)
        body = encode_forecast(package)

    with closing(open_review(review_path)) as review:
        admission_id = admit(review, body)
        received = read_admitted_forecast(review, admission_id)
        measured_target, _ = _enter_batch(review, sample, 'target')
        target_truth = seal(review, measured_target.roster_id)
        issued = report(review, admission_id, encode_truth(target_truth))

    with closing(open_review(review_path)) as review:
        reopened = read(review, issued.report_id)
    actual = {
        'training_values': [encode_fraction(row.value) for row in training_input.rows],
        'models': [[first.model_id, encode_fraction(first.parameter)], [second.model_id, encode_fraction(second.parameter)]],
        'predictions': [[row.piece_id, encode_fraction(row.first), encode_fraction(row.second)] for row in received.rows],
        'uses_correction': training_input.rows[-1].receipt_id == corrected.receipt_id,
        **_reported_scores(issued),
    }
    downstream = {
        **_reported_scores(reopened),
        'same_signed_record': reopened == issued,
        'actual_parents': (reopened.admission_id, reopened.package_id, reopened.truth_id, reopened.roster_id)
                          == (admission_id, package.package_id, target_truth.truth_id, target.roster_id),
    }
    return actual, downstream


def checked_workday(directory, check):
    sample = json.loads(_SAMPLE.read_text(encoding='utf-8'))
    actual, downstream = run_workday(directory, sample)
    expected = {
        'training_values': ['8/1', '12/1'],
        'models': [['MZ', '12/1'], ['MA', '10/1']],
        'predictions': [['B', '12/1', '10/1'], ['A', '12/1', '10/1']],
        'uses_correction': True,
        'scores': [['B', '1/1', '9/1', '-8/1'], ['A', '1/1', '1/1', '0/1']],
        'mean_delta': '-4/1',
    }
    downstream_expected = {
        'scores': [['B', '1/1', '9/1', '-8/1'], ['A', '1/1', '1/1', '0/1']],
        'mean_delta': '-4/1', 'same_signed_record': True, 'actual_parents': True,
    }
    check.assertEqual(actual, expected)
    check.assertEqual(downstream, downstream_expected)
    return {
        'case_id': 'v8', 'input': sample, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream,
        'code_paths': ['measurements/revisions.py', 'measurements/seal.py', 'training/fit.py',
                       'prediction/jobs.py', 'review/admission.py', 'review/reports.py', 'review/scoring.py'],
        'oracle': 'Manual comparison: last 12, (8+12)/2=10. For 13 the squares are 1 and 9, for 11 both are 1. The signed batch mean is (-8+0)/2=-4. Compare reopened parents to the actual issued identifiers.',
    }


class WorkdayTests(TestCase):
    def test_workday(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        checked_workday(directory, self)


def main():
    with TemporaryDirectory() as directory:
        evidence = checked_workday(Path(directory), TestCase())
        print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
