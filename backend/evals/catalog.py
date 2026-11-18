"""Every eval scenario in one list."""

from evals.scenarios import SCENARIOS as CORE
from evals.sets import adversarial, booking, multilingual

SCENARIOS = [
    *CORE,
    *adversarial.SCENARIOS,
    *booking.SCENARIOS,
    *multilingual.SCENARIOS,
]

_ids = [s.id for s in SCENARIOS]
assert len(_ids) == len(set(_ids)), "Duplicate scenario ids"