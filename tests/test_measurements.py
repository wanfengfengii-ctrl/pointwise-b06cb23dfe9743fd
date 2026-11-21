from fractions import Fraction

from measurements.intake import submit
from measurements.ledger import MeasurementLedger
from measurements.revisions import correct
from measurements.seal import read_sealed_truth, seal
from tests.support import StationTestCase


class MeasurementTests(StationTestCase):
    def test_missing_piece(self):
        roster = self.roster('H')
        submit(self.review, roster.roster_id, 'B', 'b1', 8)
        with self.assertRaisesRegex(ValueError, 'missing measurements'):
            seal(self.review, roster.roster_id)
        self.assertIsNone(MeasurementLedger(self.review).read_seal(roster.roster_id))
        self.assertEqual(self.review.execute('SELECT count(*) FROM truth_seals').fetchone()[0], 0)
        with self.assertRaises(KeyError):
            seal(self.review, 'unknown-roster')

    def test_sealed_readback(self):
        roster = self.roster('H')
        frozen, receipts = self.seal_values(roster, (8, 0))
        with self.assertRaises(ValueError):
            correct(self.review, receipts[1].receipt_id, 12, 'late-a')
        with self.assertRaises(ValueError):
            submit(self.review, roster.roster_id, 'A', 'second-a', 0)
        self.reopen_review()
        old = read_sealed_truth(self.review, frozen.truth_id)
        self.assertEqual(old, frozen)
        self.assertEqual(old.rows[1].value, Fraction(0))
        self.assertEqual(old.rows[1].receipt_id, receipts[1].receipt_id)
        self.assertEqual(old.roster.gauge, self.gauge)
        self.assertEqual(seal(self.review, roster.roster_id), frozen)
        self.assertEqual(submit(self.review, roster.roster_id, 'A', 'H.A', '0/3'), receipts[1])

    def test_receipt_replay(self):
        roster = self.roster('H')
        other = self.roster('J')
        old = submit(self.review, roster.roster_id, 'B', 'b1', '2/4')
        self.assertEqual(submit(self.review, roster.roster_id, 'B', 'b1', '0.5'), old)
        for roster_id, piece, source, value in (
            (roster.roster_id, 'B', 'b1', '3/4'),
            (roster.roster_id, 'A', 'b1', '1/2'),
            (other.roster_id, 'B', 'b1', '1/2'),
            (roster.roster_id, 'X', 'x1', 0),
            (roster.roster_id, 'B', 'new-b', '1/2'),
            (roster.roster_id, 'A', 'a1', '1/0'),
            (roster.roster_id, 'A', 'a1', None),
            (roster.roster_id, 'A', 'a1', -1),
        ):
            with self.subTest(roster=roster_id, piece=piece, source=source, value=value), self.assertRaises(ValueError):
                submit(self.review, roster_id, piece, source, value)
        with self.assertRaises(KeyError):
            submit(self.review, 'unknown-roster', 'A', 'a1', 0)
        with self.assertRaises(KeyError):
            correct(self.review, 'unknown-receipt', 1, 'a1')
        new = correct(self.review, old.receipt_id, '2/3', 'b2')
        self.assertEqual(submit(self.review, roster.roster_id, 'B', 'b1', '1/2'), old)
        self.assertEqual(MeasurementLedger(self.review).current_receipts(roster.roster_id)['B'], new)
        self.assertEqual(MeasurementLedger(self.review).get_receipt(old.receipt_id), old)

    def test_stale_correction(self):
        roster = self.roster('H')
        submit(self.review, roster.roster_id, 'B', 'b1', 8)
        old = submit(self.review, roster.roster_id, 'A', 'a1', 12)
        current = correct(self.review, old.receipt_id, 14, 'a2')
        with self.assertRaises(ValueError):
            correct(self.review, old.receipt_id, 16, 'a3')
        self.assertIsNone(MeasurementLedger(self.review).find_source('a3'))
        with self.assertRaises(ValueError):
            correct(self.review, current.receipt_id, 16, 'b1')
        truth = seal(self.review, roster.roster_id)
        self.assertEqual((truth.rows[1].receipt_id, truth.rows[1].value), (current.receipt_id, 14))
        last, mean = self.train_both(truth)
        self.assertEqual((last.parameter, mean.parameter), (14, 11))

    def test_fill_with_zero(self):
        roster = self.roster('H')
        first = submit(self.review, roster.roster_id, 'B', 'b1', 8)
        with self.assertRaises(ValueError):
            seal(self.review, roster.roster_id)
        zero = submit(self.review, roster.roster_id, 'A', 'a1', 0)
        frozen = seal(self.review, roster.roster_id)
        self.assertEqual([(row.piece_id, row.value) for row in frozen.rows], [('B', 8), ('A', 0)])
        self.assertEqual([row.receipt_id for row in frozen.rows], [first.receipt_id, zero.receipt_id])
        self.assertEqual(seal(self.review, roster.roster_id), frozen)
