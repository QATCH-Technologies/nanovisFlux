from __future__ import annotations

from .location import Location
from .steps import AspirateStep, BlowOutStep, DispenseStep, DropTipStep, PickUpTipStep
from .tip_sequence import TipSequence


def transfer(
    volume_ul: float,
    source: Location,
    dest: Location,
    *,
    tip: str | None = None,
    tip_rack: Location | None = None,
    pickup=None,
    drop_at: Location | None = None,
    blow_out: bool | Location = False,
    feed: int | None = None,
) -> list:
    """Expand a single transfer into a list of Steps: (optionally pick up a
    tip), aspirate at ``source``, dispense at ``dest``, (optionally blow out
    and drop the tip). Add the result to a Routine, or chain many of them.

    ``blow_out`` is either ``False`` (skip it), ``True`` (blow out at
    ``dest``), or a specific ``Location`` (e.g. a trash slot) to blow out
    there instead before dropping the tip.
    """
    steps = []
    if tip and tip_rack and pickup is not None:
        steps.append(PickUpTipStep(tip_rack, tip, pickup))
    steps.append(AspirateStep(volume_ul, source, feed=feed))
    steps.append(DispenseStep(volume_ul, dest, feed=feed))
    if blow_out:
        steps.append(BlowOutStep(dest if blow_out is True else blow_out))
    if drop_at is not None:
        steps.append(DropTipStep(drop_at))
    return steps


def distribute(
    volume_ul: float,
    source: Location,
    dests: list,
    *,
    tip: str,
    tips: TipSequence,
    pickup,
    trash: Location,
    blow_out: bool = True,
    feed: int | None = None,
) -> list:
    """Repeat a transfer across many destinations: fresh tip per cycle
    (pulled off ``tips``), aspirate ``volume_ul`` from the same ``source``
    every time, dispense at each of ``dests`` in turn, blow out into
    ``trash`` and drop the tip there before moving on. This is the "pick up
    a tip, aspirate, dispense, blow out, drop tip, repeat" pattern spelled
    out as one call instead of a hand-unrolled step list.
    """
    steps = []
    for dest in dests:
        steps.extend(
            transfer(
                volume_ul,
                source,
                dest,
                tip=tip,
                tip_rack=next(tips),
                pickup=pickup,
                blow_out=trash if blow_out else False,
                drop_at=trash,
                feed=feed,
            )
        )
    return steps
