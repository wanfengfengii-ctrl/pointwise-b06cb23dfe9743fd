from dataclasses import replace
from fractions import Fraction

from batches.freeze import read_frozen_roster
from batches.register import register
from batches.roster import decode_roster, encode_roster
from measurements.exchange import encode_truth
from measurements.intake import submit
from measurements.ledger import MeasurementLedger
from measurements.revisions import correct
from measurements.seal import seal
from tests.support import StationTestCase
from training.admission import read_training_truth
from training.catalog import read_model
from training.fit import train
from training.strategies import LAST_PIECE, MEAN


class TrainingTests(StationTestCase):
    def test_exact_models(self):
        roster = self.roster('H')
        truth, _ = self.seal_values(roster, (8, 12))
        last, mean = self.train_both(truth)
        self.assertEqual((last.parameter, mean.parameter), (Fraction(12), Fraction(10)))
        self.assertEqual((last.truth_id, mean.truth_id), (truth.truth_id, truth.truth_id))
        self.assertEqual(read_training_truth(self.prediction, truth.truth_id), truth)

    def test_correction_before_seal(self):
        roster = self.roster('H')
        submit(self.review, roster.roster_id, 'B', 'b1', 8)
        prior = submit(self.review, roster.roster_id, 'A', 'a1', 12)
        changed = correct(self.review, prior.receipt_id, 14, 'a2')
        truth = seal(self.review, roster.roster_id)
        last, mean = self.train_both(truth)
        self.assertEqual((last.parameter, mean.parameter), (Fraction(14), Fraction(11)))
        self.assertEqual(truth.rows[-1].receipt_id, changed.receipt_id)
        self.assertEqual(changed.previous_id, prior.receipt_id)

    def test_registration(self):
        roster = self.roster('H', nominal='22/2')
        self.assertEqual(register(self.review, 'H', self.gauge.gauge_id, '11.0', ['B', 'A']), roster)
        self.assertEqual(decode_roster(encode_roster(roster)), roster)
        for batch, nominal, pieces in (
            ('DUP', 11, ('A', 'A')),
            ('ZERO', 0, ('A',)),
            ('NEG', -1, ('A',)),
            ('EMPTY', 11, ()),
            ('H', 11, ('A', 'B')),
        ):
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                self.roster(batch, pieces, nominal)
        with self.assertRaises(KeyError):
            register(self.review, 'UNKNOWN', 'missing-gauge', 11, ('A',))
        self.assertEqual(read_frozen_roster(self.review, roster.roster_id), roster)

    def test_roster_order(self):
        roster = self.roster('H')
        entered_first = submit(self.review, roster.roster_id, 'A', 'a1', 12)
        entered_second = submit(self.review, roster.roster_id, 'B', 'b1', 8)
        truth = seal(self.review, roster.roster_id)
        self.assertEqual([row.piece_id for row in truth.rows], ['B', 'A'])
        self.assertEqual([row.receipt_id for row in truth.rows], [entered_second.receipt_id, entered_first.receipt_id])
        last, mean = self.train_both(truth)
        self.assertEqual((last.parameter, mean.parameter), (Fraction(12), Fraction(10)))

    def test_exact_fraction(self):
        truth, _ = self.seal_values(self.roster('H', ('B', 'A', 'C')), ('1/3', '2/3', '4/3'))
        last, mean = self.train_both(truth)
        self.reopen_prediction()
        self.assertEqual(read_model(self.prediction, last.model_id).parameter, Fraction(4, 3))
        self.assertEqual(read_model(self.prediction, mean.model_id).parameter, Fraction(7, 9))

    def test_model_binding(self):
        truth, _ = self.seal_values(self.roster('H'), (8, 12))
        other, _ = self.seal_values(self.roster('J'), (8, 12))
        model = train(self.prediction, truth, 'M', LAST_PIECE)
        self.assertEqual(train(self.prediction, encode_truth(truth), 'M', LAST_PIECE), model)
        for item, name, strategy in (
            (other, 'M', LAST_PIECE),
            (truth, 'M', MEAN),
            (truth, 'BAD', 'weighted'),
            (replace(truth, rows=()), 'EMPTY', MEAN),
        ):
            with self.subTest(name=name, strategy=strategy), self.assertRaises(ValueError):
                train(self.prediction, item, name, strategy)
        self.assertEqual(read_model(self.prediction, 'M'), model)
        with self.assertRaises(KeyError):
            read_training_truth(self.prediction, other.truth_id)
        with self.assertRaises(KeyError):
            read_model(self.prediction, 'EMPTY')

    def test_sealed_provenance(self):
        roster = self.roster('H')
        submit(self.review, roster.roster_id, 'B', 'history-b', 8)
        old = submit(self.review, roster.roster_id, 'A', 'history-a', 12)
        revised = correct(self.review, old.receipt_id, 14, 'history-a-correction')
        frozen = seal(self.review, roster.roster_id)
        original = MeasurementLedger(self.review).get_receipt(old.receipt_id)
        self.assertEqual((original.value, original.source), (12, 'history-a'))
        self.assertEqual((frozen.rows[-1].value, frozen.rows[-1].receipt_id, frozen.rows[-1].source),
                         (14, revised.receipt_id, 'history-a-correction'))
        self.close_review()
        model = train(self.prediction, encode_truth(frozen), 'M', LAST_PIECE)
        self.reopen_prediction()
        accepted = read_training_truth(self.prediction, read_model(self.prediction, model.model_id).truth_id)
        self.assertEqual((accepted.rows[-1].value, accepted.rows[-1].receipt_id, accepted.rows[-1].source),
                         (14, revised.receipt_id, 'history-a-correction'))
        self.assertEqual(model.parameter, 14)
