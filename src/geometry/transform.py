from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


def _solve3(a: list, b: list) -> list:
    """Gaussian elimination for a 3x3 system (dependency-free)."""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("degenerate calibration points (collinear?)")
        m[col], m[piv] = m[piv], m[col]
        pivot = m[col][col]
        m[col] = [x / pivot for x in m[col]]
        for r in range(3):
            if r != col:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[0][3], m[1][3], m[2][3]]


@dataclass(frozen=True)
class AffineTransform2D:
    """Maps (x, y) -> (a x + b y + tx, c x + d y + ty). Rich enough to absorb
    offset, scale, rotation and skew between the deck and motor frames."""

    a: float
    b: float
    tx: float
    c: float
    d: float
    ty: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.b * y + self.tx, self.c * x + self.d * y + self.ty)

    def inverse(self) -> "AffineTransform2D":
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            raise ValueError("non-invertible transform")
        ia, ib = self.d / det, -self.b / det
        ic, id_ = -self.c / det, self.a / det
        return AffineTransform2D(
            ia, ib, -(ia * self.tx + ib * self.ty), ic, id_, -(ic * self.tx + id_ * self.ty)
        )

    @classmethod
    def from_point_pairs(cls, src: Sequence, dst: Sequence) -> "AffineTransform2D":
        """Least-squares affine fit from src[i] -> dst[i], for 3 or more
        (non-collinear) pairs. Exact for exactly 3 points; a best fit for
        more (overdetermined) points.

        Both cases go through the same normal-equations 3x3 system --
        ``(AtA) theta = At d``, solved with the dependency-free ``_solve3``
        above -- rather than numpy.lstsq, so this stays a lightweight,
        dependency-free module. For exactly 3 non-collinear points this
        reduces to the same unique answer a direct solve would give (AtA is
        then square and invertible, so the normal equations and the direct
        system share one solution)."""
        if len(src) != len(dst):
            raise ValueError("src and dst must have the same number of points")
        if len(src) < 3:
            raise ValueError("need at least three calibration point pairs")
        rows = [[sx, sy, 1.0] for sx, sy in src]
        ata = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
        atx = [sum(r[i] * d[0] for r, d in zip(rows, dst)) for i in range(3)]
        aty = [sum(r[i] * d[1] for r, d in zip(rows, dst)) for i in range(3)]
        abx = _solve3(ata, atx)
        cdy = _solve3(ata, aty)
        return cls(abx[0], abx[1], abx[2], cdy[0], cdy[1], cdy[2])
