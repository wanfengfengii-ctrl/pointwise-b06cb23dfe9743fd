"""Exercise the public online backtest handoff after it is implemented."""
import json
import unittest
from fractions import Fraction

from tests.support import ReplyLost, StationTestCase, discard_reply


def reformatted(body):
    return json.dumps(json.loads(body), indent=2)


class OnlineShift(StationTestCase):
    def test_recover_original_cutoff(self):
        from batches.registry import RosterRegistry
        from measurements.intake import submit_online
        from prediction.jobs import begin_online, collect_online
        from review.admission import (
            accept_online_commitment, accept_online_prediction, make_online_observation,
        )
        from review.reports import read_online_report, report_online
        from training.admission import admit_online_observation, online_training_size

        roster = self.roster("T", ("B", "A", "P", "Q", "R"), nominal=11)
        batch = roster.batch_id
        RosterRegistry(self.prediction).save_snapshot(roster)
        for position, piece, value in ((1, "A", 8), (2, "B", 12)):
            submit_online(self.review, batch, piece, f"T.{piece}", value)
            commitment = begin_online(self.prediction, batch, piece)
            accept_online_commitment(self.review, batch, piece, commitment)
            if position == 1:
                a_prediction = collect_online(self.prediction, batch, piece)
                accept_online_prediction(self.review, batch, piece, a_prediction)
                a_report = report_online(self.review, batch, piece)
                self.assertEqual((a_report["cutoff"], a_report["first"], a_report["second"], a_report["delta"]),
                                 (0, 11, 11, 0))
            observation = make_online_observation(self.review, batch, piece)
            self.assertEqual(admit_online_observation(self.prediction, observation), position)

        p_receipt = submit_online(self.review, batch, "P", "T.P", 13)
        self.assertEqual(submit_online(self.review, batch, "P", "T.P-copy", "26/2"), p_receipt)
        with self.assertRaises(ValueError):
            submit_online(self.review, batch, "P", "T.P-other", 14)
        self.assertIsNone(make_online_observation(self.review, batch, "P"))
        self.assertIsNone(report_online(self.review, batch, "P"))
        self.assertEqual(online_training_size(self.prediction, batch), 2)
        with self.assertRaises(ReplyLost):
            discard_reply(begin_online, self.prediction, batch, "P")

        q_commitment = begin_online(self.prediction, batch, "Q")
        with self.assertRaises(ValueError):
            accept_online_commitment(self.review, batch, "P", q_commitment)
        self.assertIsNone(make_online_observation(self.review, batch, "P"))
        submit_online(self.review, batch, "Q", "T.Q", 30)
        accept_online_commitment(self.review, batch, "Q", q_commitment)
        q_observation = make_online_observation(self.review, batch, "Q")
        self.assertEqual(admit_online_observation(self.prediction, q_observation), 3)
        self.reopen_review()
        self.reopen_prediction()

        p_commitment = begin_online(self.prediction, batch, "P")
        accept_online_commitment(self.review, batch, "P", p_commitment)
        accept_online_commitment(self.review, batch, "P", reformatted(p_commitment))
        self.assertIsNone(report_online(self.review, batch, "P"))
        p_observation = make_online_observation(self.review, batch, "P")
        self.assertEqual(admit_online_observation(self.prediction, p_observation), 4)
        self.assertEqual(admit_online_observation(self.prediction, reformatted(p_observation)), 4)
        self.assertEqual(online_training_size(self.prediction, batch), 4)

        self.close_review()
        p_prediction = collect_online(self.prediction, batch, "P")
        r_commitment = begin_online(self.prediction, batch, "R")
        r_prediction = collect_online(self.prediction, batch, "R")
        self.close_prediction()
        self.reopen_review()
        with self.assertRaises(ValueError):
            accept_online_prediction(self.review, batch, "P", a_prediction)
        self.assertIsNone(report_online(self.review, batch, "P"))
        accept_online_prediction(self.review, batch, "P", p_prediction)
        p_report = report_online(self.review, batch, "P")
        self.assertEqual((p_report["batch_id"], p_report["roster_id"], p_report["piece_id"], p_report["receipt_id"]),
                         (batch, roster.roster_id, "P", p_receipt.receipt_id))
        self.assertEqual((p_report["cutoff"], p_report["first"], p_report["second"],
                          p_report["actual"], p_report["delta"]), (2, 12, 10, 13, -8))
        for field in ("first", "second", "actual", "delta"):
            self.assertIsInstance(p_report[field], Fraction)

        accept_online_commitment(self.review, batch, "R", r_commitment)
        accept_online_prediction(self.review, batch, "R", r_prediction)
        self.assertIsNone(report_online(self.review, batch, "R"))
        submit_online(self.review, batch, "R", "T.R", 14)
        r_report = report_online(self.review, batch, "R")
        self.assertEqual((r_report["cutoff"], r_report["first"], r_report["second"], r_report["delta"]),
                         (4, 13, Fraction(63, 4), Fraction(-33, 16)))
        self.reopen_review()
        self.assertEqual(read_online_report(self.review, p_report["report_id"]), p_report)
        self.assertEqual(report_online(self.review, batch, "P"), p_report)
        self.reopen_prediction()
        self.assertEqual(json.loads(begin_online(self.prediction, batch, "P")), json.loads(p_commitment))
        self.assertEqual(json.loads(collect_online(self.prediction, batch, "P")), json.loads(p_prediction))
        print("ONLINE_SHIFT " + json.dumps({"P": p_report, "R": r_report}, default=str, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
