from batches.gauges import read_gauge, register_gauge
from batches.registry import RosterRegistry
from measurements.ledger import MeasurementLedger
from measurements.seal import read_sealed_truth
from tests.support import StationTestCase
from training.admission import read_training_truth
from training.catalog import read_model


class InitializationTests(StationTestCase):
    def test_reinitialize(self):
        gauge = register_gauge(self.review, 'G-USER', 'custom calibration ticket')
        history = self.roster('H')
        truth, receipts = self.seal_values(history, (0, 12))
        first, second = self.train_both(truth)
        self.reopen_review()
        self.reopen_prediction()
        self.reopen_review()
        self.reopen_prediction()
        self.assertEqual(read_gauge(self.review, gauge.gauge_id), gauge)
        self.assertEqual(register_gauge(self.review, gauge.gauge_id, gauge.provenance), gauge)
        with self.assertRaises(ValueError):
            register_gauge(self.review, gauge.gauge_id, 'different ticket')
        self.assertEqual(read_sealed_truth(self.review, truth.truth_id), truth)
        self.assertEqual(read_sealed_truth(self.review, truth.truth_id).rows[0].value, 0)
        self.assertEqual(MeasurementLedger(self.review).get_receipt(receipts[0].receipt_id), receipts[0])
        self.assertEqual(RosterRegistry(self.prediction).read_snapshot(history.roster_id), history)
        self.assertEqual(read_training_truth(self.prediction, truth.truth_id), truth)
        self.assertEqual(read_model(self.prediction, 'MZ'), first)
        self.assertEqual(read_model(self.prediction, 'MA'), second)
        more, _ = self.seal_values(self.roster('J'), (1, 3))
        models = self.train_both(more, ('JZ', 'JA'))
        self.assertEqual((models[0].parameter, models[1].parameter), (3, 2))
