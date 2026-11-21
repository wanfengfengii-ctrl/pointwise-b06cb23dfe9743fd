from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from batches.gauges import register_gauge
from batches.register import register
from batches.registry import RosterRegistry
from measurements.intake import submit
from measurements.seal import seal
from prediction.jobs import forecast
from prediction.receipts import open_prediction
from review.store import open_review
from training.fit import train
from training.strategies import LAST_PIECE, MEAN


class ReplyLost(ConnectionError):
    pass


def discard_reply(operation, *args, **kwargs):
    operation(*args, **kwargs)
    raise ReplyLost('reply discarded after the operation returned')


def install_report_commit_failure(db, final_position):
    # The deferred constraint is violated by the final real detail insert.
    # SQLite checks it on COMMIT after all regular inserts have run.
    if type(final_position) is not int or final_position < 0:
        raise ValueError('expected a zero-based final position')
    db.executescript(f'''
        CREATE TABLE fixture_commit_parent (id INTEGER PRIMARY KEY);
        CREATE TABLE fixture_commit_child (
            parent_id INTEGER REFERENCES fixture_commit_parent(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TRIGGER fixture_fail_report_commit AFTER INSERT ON report_pieces
        WHEN NEW.position = {final_position}
        BEGIN
            INSERT INTO fixture_commit_child (parent_id) VALUES (1);
        END;
    ''')


def remove_report_commit_failure(db):
    db.executescript('''
        DROP TRIGGER fixture_fail_report_commit;
        DROP TABLE fixture_commit_child;
        DROP TABLE fixture_commit_parent;
    ''')


class StationTestCase(TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.review_path = directory / 'review.sqlite3'
        self.prediction_path = directory / 'prediction.sqlite3'
        self.review = None
        self.prediction = None
        self.addCleanup(self.close_prediction)
        self.addCleanup(self.close_review)
        self.reopen_review()
        self.reopen_prediction()
        self.gauge = register_gauge(self.review, 'G-17', 'calibration QC-17')

    def close_review(self):
        if self.review is not None:
            self.review.close()
            self.review = None

    def close_prediction(self):
        if self.prediction is not None:
            self.prediction.close()
            self.prediction = None

    def reopen_review(self):
        self.close_review()
        self.review = open_review(self.review_path)

    def reopen_prediction(self):
        self.close_prediction()
        self.prediction = open_prediction(self.prediction_path)

    def roster(self, batch, pieces=('B', 'A'), nominal=11):
        return register(self.review, batch, self.gauge.gauge_id, nominal, pieces)

    def seal_values(self, roster, values):
        receipts = tuple(
            submit(self.review, roster.roster_id, piece, f'{roster.batch_id}.{piece}', value)
            for piece, value in zip(roster.pieces, values, strict=True)
        )
        return seal(self.review, roster.roster_id), receipts

    def train_both(self, truth, names=('MZ', 'MA')):
        return (train(self.prediction, truth, names[0], LAST_PIECE),
                train(self.prediction, truth, names[1], MEAN))

    def prepare_forecast(self, history=(8, 12)):
        truth, _ = self.seal_values(self.roster('H'), history)
        models = self.train_both(truth)
        target = self.roster('T')
        RosterRegistry(self.prediction).save_snapshot(target)
        package = forecast(self.prediction, target.roster_id, models[0].model_id, models[1].model_id)
        return target, models, package
