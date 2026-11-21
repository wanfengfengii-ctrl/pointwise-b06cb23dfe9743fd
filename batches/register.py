from batches.freeze import freeze_roster
from batches.gauges import read_gauge
from batches.roster import require_piece_order
from batches.units import parse_um, require_identifier


def register(db, batch_id, gauge_id, nominal_um, pieces):
    require_identifier(batch_id, 'batch ID')
    nominal = parse_um(nominal_um)
    if nominal <= 0:
        raise ValueError('nominal thickness must be positive')
    ordered_pieces = require_piece_order(pieces)
    gauge = read_gauge(db, gauge_id)
    return freeze_roster(db, batch_id, gauge, nominal, ordered_pieces)
