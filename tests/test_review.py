import sqlite3
from contextlib import closing
from dataclasses import replace
from fractions import Fraction

from measurements.exchange import encode_truth
from prediction.jobs import forecast
from review.admission import admit
from review.reports import read, report
from review.store import ReviewStore, open_review
from tests.support import StationTestCase, install_report_commit_failure, remove_report_commit_failure


class ReviewTests(StationTestCase):
    def test_mixed_roster(self):
        target, _, package = self.prepare_forecast()
        incoming = admit(self.review, package)
        other, _ = self.seal_values(self.roster('OTHER', ('C', 'A')), (13, 11))
        with self.assertRaises(ValueError):
            report(self.review, incoming, other)
        self.assertEqual(self.review.execute('SELECT count(*) FROM review_reports').fetchone()[0], 0)
        truth, _ = self.seal_values(target, (13, 11))
        with self.assertRaises(KeyError):
            report(self.review, 'unknown-admission', truth)
        with self.assertRaises(ValueError):
            report(self.review, incoming, replace(truth, rows=()))
        with self.assertRaises(ValueError):
            report(self.review, incoming, replace(truth, truth_id='unknown-truth'))
        self.assertEqual(report(self.review, incoming, truth).truth_id, truth.truth_id)

    def test_same_piece_set(self):
        target, _, package = self.prepare_forecast()
        incoming = admit(self.review, package)
        other, _ = self.seal_values(self.roster('OTHER'), (13, 11))
        self.assertEqual((other.roster.pieces, other.roster.gauge, other.roster.nominal_um),
                         (target.pieces, target.gauge, target.nominal_um))
        self.assertNotEqual(other.roster.roster_id, target.roster_id)
        with self.assertRaisesRegex(ValueError, 'same frozen roster'):
            report(self.review, incoming, other)
        self.assertEqual(self.review.execute('SELECT count(*) FROM review_reports').fetchone()[0], 0)
        truth, _ = self.seal_values(target, (13, 11))
        issued = report(self.review, incoming, truth)
        self.assertEqual((issued.truth_id, issued.roster_id), (truth.truth_id, target.roster_id))

    def test_reopen_report(self):
        target, _, package = self.prepare_forecast()
        self.close_prediction()
        incoming = admit(self.review, package)
        truth, _ = self.seal_values(target, (13, 11))
        issued = report(self.review, incoming, truth)
        self.assertEqual([(p.piece_id, p.first_squared, p.second_squared, p.delta) for p in issued.pieces],
                         [('B', 1, 9, -8), ('A', 1, 1, 0)])
        self.assertEqual(issued.mean_delta, Fraction(-4))
        self.assertEqual((issued.admission_id, issued.package_id, issued.truth_id, issued.roster_id),
                         (incoming, package.package_id, truth.truth_id, target.roster_id))
        self.reopen_review()
        self.assertEqual(read(self.review, issued.report_id), issued)
        self.assertEqual(report(self.review, incoming, encode_truth(truth)), issued)

    def test_fractional_score(self):
        target, _, package = self.prepare_forecast(history=(0, '3/2'))
        # A separate mean model supplies 1/2, while the historical last terminates at 3/2.
        other, _ = self.seal_values(self.roster('J'), ('1/4', '3/4'))
        _, mean = self.train_both(other, ('JZ', 'JA'))
        issued = forecast(self.prediction, target, package.first_model.model_id, mean.model_id)
        self.assertEqual((issued.rows[0].first, issued.rows[0].second), (Fraction(3, 2), Fraction(1, 2)))
        truth, _ = self.seal_values(target, ('5/4', 1))
        result = report(self.review, admit(self.review, issued), truth)
        self.assertEqual([(p.first_squared, p.second_squared, p.delta) for p in result.pieces],
                         [(Fraction(1, 16), Fraction(9, 16), Fraction(-1, 2)),
                          (Fraction(1, 4), Fraction(1, 4), Fraction(0))])
        self.assertEqual(result.mean_delta, Fraction(-1, 4))

    def test_fixed_parents(self):
        target, _, original_package = self.prepare_forecast()
        admission_id = admit(self.review, original_package)
        truth, _ = self.seal_values(target, (13, 11))
        original = report(self.review, admission_id, truth)
        new_package = forecast(self.prediction, target.roster_id, 'MA', 'MZ')
        new_admission = admit(self.review, new_package)
        changed = report(self.review, new_admission, truth)
        self.assertNotEqual(changed.report_id, original.report_id)
        self.assertEqual((original.mean_delta, changed.mean_delta), (-4, 4))
        self.close_prediction()
        self.reopen_review()
        self.assertEqual(read(self.review, original.report_id), original)
        self.assertEqual(read(self.review, changed.report_id), changed)
        self.assertEqual((original.admission_id, original.package_id, original.truth_id),
                         (admission_id, original_package.package_id, truth.truth_id))
        with self.assertRaises(KeyError):
            read(self.review, 'unknown-report')

    def test_failed_commit(self):
        target, _, package = self.prepare_forecast()
        truth, _ = self.seal_values(target, (13, 11))
        admission_id = admit(self.review, package)
        install_report_commit_failure(self.review, final_position=1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            report(self.review, admission_id, truth)
        self.assertFalse(self.review.in_transaction)
        with closing(open_review(self.review_path)) as observer:
            self.assertEqual(observer.execute('SELECT count(*) FROM review_reports').fetchone()[0], 0)
            self.assertEqual(observer.execute('SELECT count(*) FROM report_pieces').fetchone()[0], 0)
            self.assertIsNone(ReviewStore(observer).find_report_for_parents(admission_id, truth.truth_id))
            remove_report_commit_failure(observer)
        issued = report(self.review, admission_id, truth)
        self.reopen_review()
        self.assertEqual(report(self.review, admission_id, truth), issued)
        self.assertEqual(read(self.review, issued.report_id), issued)
        self.assertEqual([row.piece_id for row in issued.pieces], ['B', 'A'])
        self.assertEqual(issued.mean_delta, -4)
        self.assertEqual(self.review.execute('SELECT count(*) FROM review_reports').fetchone()[0], 1)
        self.assertEqual(self.review.execute('SELECT count(*) FROM report_pieces').fetchone()[0], 2)
