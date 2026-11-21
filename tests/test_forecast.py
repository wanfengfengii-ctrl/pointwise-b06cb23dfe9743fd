import json
from dataclasses import replace

from batches.registry import RosterRegistry
from prediction.jobs import forecast
from prediction.package import encode_forecast
from prediction.receipts import read_forecast
from review.admission import admit, read_admitted_forecast
from review.store import ReviewStore
from tests.support import ReplyLost, StationTestCase, discard_reply


class ForecastTests(StationTestCase):
    def test_ordered_pair(self):
        roster, models, package = self.prepare_forecast()
        self.assertEqual([row.piece_id for row in package.rows], ['B', 'A'])
        self.assertEqual([(row.first, row.second) for row in package.rows], [(12, 10), (12, 10)])
        self.assertEqual((package.first_model.model_id, package.second_model.model_id), ('MZ', 'MA'))
        self.assertEqual((package.first_model.truth_id, package.second_model.truth_id),
                         (models[0].truth_id, models[1].truth_id))
        self.assertEqual(forecast(self.prediction, roster, 'MZ', 'MA'), package)
        admission_id = admit(self.review, package)
        equivalent = json.dumps(json.loads(encode_forecast(package)), indent=2)
        self.assertEqual(admit(self.review, equivalent), admission_id)
        self.assertEqual(read_admitted_forecast(self.review, admission_id), package)

    def test_conflicting_package(self):
        roster, _, first = self.prepare_forecast()
        other = forecast(self.prediction, roster.roster_id, 'MA', 'MZ')
        admission_id = admit(self.review, first)
        self.assertEqual(admit(self.review, first), admission_id)
        with self.assertRaises(ValueError):
            admit(self.review, replace(other, package_id=first.package_id))
        self.assertEqual(read_admitted_forecast(self.review, admission_id), first)
        self.assertEqual(self.review.execute('SELECT count(*) FROM forecast_admissions').fetchone()[0], 1)

    def test_reverse_slots(self):
        roster, _, first = self.prepare_forecast()
        reverse = forecast(self.prediction, roster, 'MA', 'MZ')
        self.assertNotEqual(first.package_id, reverse.package_id)
        self.assertEqual((reverse.first_model, reverse.second_model), (first.second_model, first.first_model))
        for package, values in ((first, (12, 10)), (reverse, (10, 12))):
            admission_id = admit(self.review, package)
            stored = read_admitted_forecast(self.review, admission_id)
            self.assertEqual(stored, package)
            self.assertEqual([row.piece_id for row in stored.rows], ['B', 'A'])
            self.assertEqual([(row.first, row.second) for row in stored.rows], [values, values])

    def test_isolated_read(self):
        target, _, issued = self.prepare_forecast()
        self.reopen_prediction()
        self.assertEqual(read_forecast(self.prediction, issued.package_id), issued)
        self.assertEqual(RosterRegistry(self.prediction).read_snapshot(target.roster_id), target)
        with self.assertRaises(ValueError):
            forecast(self.prediction, replace(target, pieces=('A', 'A')), 'MZ', 'MA')
        different = replace(target, pieces=('A', 'B'))
        with self.assertRaises(ValueError):
            RosterRegistry(self.prediction).save_snapshot(different)
        with self.assertRaises(ValueError):
            forecast(self.prediction, different, 'MZ', 'MA')
        with self.assertRaises(KeyError):
            forecast(self.prediction, target.roster_id, 'MZ', 'unknown-model')
        with self.assertRaises(KeyError):
            forecast(self.prediction, 'unknown-roster', 'MZ', 'MA')
        self.assertEqual(RosterRegistry(self.prediction).read_snapshot(target.roster_id), target)
        self.close_prediction()
        self.reopen_review()
        admission_id = admit(self.review, encode_forecast(issued))
        self.reopen_review()
        self.assertEqual(read_admitted_forecast(self.review, admission_id), issued)

    def test_lost_admit_reply(self):
        _, _, package = self.prepare_forecast()
        self.close_prediction()
        with self.assertRaises(ReplyLost):
            discard_reply(admit, self.review, package)
        self.reopen_review()
        first = ReviewStore(self.review).find_admission_by_package(package.package_id)
        self.assertIsNotNone(first)
        admission_id = admit(self.review, encode_forecast(package))
        self.assertEqual(admission_id, first[0])
        self.assertEqual(read_admitted_forecast(self.review, admission_id), package)
        self.assertEqual(self.review.execute('SELECT count(*) FROM forecast_admissions').fetchone()[0], 1)

    def test_bad_package(self):
        _, _, package = self.prepare_forecast()
        admission_id = admit(self.review, package)
        malformed = json.loads(encode_forecast(package))
        malformed['rows'][0]['first'] = '5/0'
        for bad in (replace(package, rows=package.rows[:1]),
                    replace(package, rows=(package.rows[0], package.rows[0])), json.dumps(malformed)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                admit(self.review, bad)
        self.assertEqual(read_admitted_forecast(self.review, admission_id), package)
        self.assertEqual(self.review.execute('SELECT count(*) FROM forecast_admissions').fetchone()[0], 1)
