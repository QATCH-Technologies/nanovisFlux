"""AffineTransform2D.from_point_pairs: exact for 3 non-collinear points,
least-squares best fit for more (overdetermined) points -- both solved via
the same dependency-free normal-equations 3x3 system (see
geometry.transform._solve3), not numpy."""
import pytest

from src.geometry import AffineTransform2D

#: An arbitrary rotate+scale+translate affine to generate consistent
#: synthetic point pairs from -- deliberately not axis-aligned, so a bug
#: that only handles the identity/scale-only case would still be caught.
_TRUE = AffineTransform2D(a=1.8, b=-0.6, tx=50.0, c=0.6, d=1.8, ty=-20.0)

_SRC_3 = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]
_SRC_5 = _SRC_3 + [(10.0, 10.0), (4.0, 7.0)]


def _dst_from(src, transform=_TRUE):
    return [transform.apply(x, y) for x, y in src]


def test_exact_fit_with_three_points_recovers_transform():
    fitted = AffineTransform2D.from_point_pairs(_SRC_3, _dst_from(_SRC_3))
    for field in ("a", "b", "tx", "c", "d", "ty"):
        assert getattr(fitted, field) == pytest.approx(getattr(_TRUE, field), abs=1e-9)


def test_overdetermined_consistent_points_recover_exact_transform():
    """5 points generated from the same transform (zero residual, just an
    overdetermined system) should still recover it exactly -- the least
    squares fit reduces to the exact answer when the data is consistent."""
    fitted = AffineTransform2D.from_point_pairs(_SRC_5, _dst_from(_SRC_5))
    for field in ("a", "b", "tx", "c", "d", "ty"):
        assert getattr(fitted, field) == pytest.approx(getattr(_TRUE, field), abs=1e-6)
    for x, y in _SRC_5:
        fx, fy = fitted.apply(x, y)
        tx, ty = _TRUE.apply(x, y)
        assert fx == pytest.approx(tx, abs=1e-6)
        assert fy == pytest.approx(ty, abs=1e-6)


def test_overdetermined_noisy_points_best_fit_is_close_but_not_exact():
    dst = _dst_from(_SRC_5)
    noisy = list(dst)
    noisy[-1] = (noisy[-1][0] + 0.5, noisy[-1][1] - 0.5)  # perturb one point

    fitted = AffineTransform2D.from_point_pairs(_SRC_5, noisy)

    # Close to the true transform (small perturbation spread over 5 points)
    # but not an exact match -- least squares absorbs the noise rather than
    # reproducing it exactly.
    assert fitted.a == pytest.approx(_TRUE.a, abs=0.2)
    assert fitted.d == pytest.approx(_TRUE.d, abs=0.2)
    assert (fitted.a, fitted.b, fitted.tx, fitted.c, fitted.d, fitted.ty) != \
           (_TRUE.a, _TRUE.b, _TRUE.tx, _TRUE.c, _TRUE.d, _TRUE.ty)

    # And it should fit the noisy data at least as well as the true
    # transform does (that's what "least squares" means) -- total squared
    # residual over all 5 points must not be worse than the un-fitted true
    # transform's own residual on the same noisy targets.
    def sse(t):
        total = 0.0
        for (sx, sy), (dx, dy) in zip(_SRC_5, noisy):
            fx, fy = t.apply(sx, sy)
            total += (fx - dx) ** 2 + (fy - dy) ** 2
        return total

    assert sse(fitted) <= sse(_TRUE) + 1e-9


def test_requires_at_least_three_points():
    with pytest.raises(ValueError):
        AffineTransform2D.from_point_pairs(_SRC_3[:2], _dst_from(_SRC_3[:2]))


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        AffineTransform2D.from_point_pairs(_SRC_3, _dst_from(_SRC_3)[:2])


@pytest.mark.parametrize("n", [3, 5])
def test_collinear_points_raise(n):
    collinear = [(float(i), float(i)) for i in range(n)]
    with pytest.raises(ValueError):
        AffineTransform2D.from_point_pairs(collinear, _dst_from(collinear))
