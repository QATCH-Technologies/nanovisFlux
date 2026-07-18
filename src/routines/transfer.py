from __future__ import annotations
from .location import Location
from .steps import (PickUpTipStep, AspirateStep, DispenseStep, BlowOutStep,
                    DropTipStep)


def transfer(volume_ul: float, source: Location, dest: Location, *,
             tip: str | None = None, tip_rack: Location | None = None,
             pickup=None, drop_at: Location | None = None,
             blow_out: bool = False, feed: int | None = None) -> list:
    """Expand a single transfer into a list of Steps: (optionally pick up a
    tip), aspirate at ``source``, dispense at ``dest``, (optionally blow out
    and drop the tip). Add the result to a Routine, or chain many of them."""
    steps = []
    if tip and tip_rack and pickup is not None:
        steps.append(PickUpTipStep(tip_rack, tip, pickup))
    steps.append(AspirateStep(volume_ul, source, feed=feed))
    steps.append(DispenseStep(volume_ul, dest, feed=feed))
    if blow_out:
        steps.append(BlowOutStep(dest))
    if drop_at is not None:
        steps.append(DropTipStep(drop_at))
    return steps
