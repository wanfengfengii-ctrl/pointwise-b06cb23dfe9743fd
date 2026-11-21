from batches.registry import write_transaction
from batches.units import require_identifier
from training.admission import admit_training_truth
from training.catalog import ModelVersion, publish_model
from training.strategies import STRATEGIES, require_strategy


def train(db, truth, model_id, strategy):
    require_identifier(model_id, 'model ID')
    calculate = STRATEGIES[require_strategy(strategy)]
    with write_transaction(db):
        accepted = admit_training_truth(db, truth)
        parameter = calculate(accepted.rows)
        return publish_model(db, ModelVersion(model_id, accepted.truth_id, strategy, parameter))
