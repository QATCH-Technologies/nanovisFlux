"""Two-dimensional affine transforms for calibrated coordinate conversion.

This module provides a dependency-free affine transformation type for mapping
between two-dimensional coordinate frames. It supports translation, scaling,
rotation, and skew, making it suitable for converting between physical deck
coordinates and motor coordinates when the two frames are not perfectly
axis-aligned.

Transforms can be inverted and can be fitted from three or more corresponding
source and destination points using least-squares estimation. The fitting
implementation uses a small Gaussian-elimination solver rather than requiring
an external numerical dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def _solve3(a: list, b: list) -> list:
    """Solve a 3x3 linear system using Gaussian elimination.

    Args:
        a: Three-by-three coefficient matrix.
        b: Three-element right-hand-side vector.

    Returns:
        list: Three-element solution vector.

    Raises:
        ValueError: If the coefficient matrix is singular or numerically
            degenerate.
    """
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
    """Represent a two-dimensional affine coordinate transformation.

    The transform maps a source point ``(x, y)`` to a destination point using
    the equations::

        x' = a*x + b*y + tx
        y' = c*x + d*y + ty

    The linear component can represent rotation, independent scaling, and
    skew, while ``tx`` and ``ty`` represent translation. This makes the
    transform suitable for calibration between physical and machine
    coordinate frames.

    Attributes:
        a: X contribution to the transformed X coordinate.
        b: Y contribution to the transformed X coordinate.
        tx: Translation applied to the transformed X coordinate.
        c: X contribution to the transformed Y coordinate.
        d: Y contribution to the transformed Y coordinate.
        ty: Translation applied to the transformed Y coordinate.
    """

    a: float
    b: float
    tx: float
    c: float
    d: float
    ty: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        """Transform a two-dimensional point into the destination frame.

        Args:
            x: Source-frame X coordinate.
            y: Source-frame Y coordinate.

        Returns:
            tuple[float, float]: Transformed ``(x, y)`` coordinates.
        """
        return (self.a * x + self.b * y + self.tx, self.c * x + self.d * y + self.ty)

    def inverse(self) -> AffineTransform2D:
        """Return the inverse coordinate transformation.

        The inverse maps points from the destination frame back into the source
        frame. The linear portion must be nonsingular for an inverse to exist.

        Returns:
            AffineTransform2D: A transform that reverses this transform.

        Raises:
            ValueError: If the linear portion of the transform has a zero or
                numerically negligible determinant and therefore cannot be
                inverted.
        """
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            raise ValueError("non-invertible transform")
        ia, ib = self.d / det, -self.b / det
        ic, id_ = -self.c / det, self.a / det
        return AffineTransform2D(
            ia, ib, -(ia * self.tx + ib * self.ty), ic, id_, -(ic * self.tx + id_ * self.ty)
        )

    @classmethod
    def from_point_pairs(
        cls,
        src: Sequence,
        dst: Sequence,
    ) -> AffineTransform2D:
        """Fit an affine transform from corresponding source and destination points.

        The method estimates the transform satisfying ``src[i] -> dst[i]`` for
        three or more corresponding two-dimensional points. With exactly three
        non-collinear pairs, the resulting transform is the unique exact affine
        solution. With additional pairs, a least-squares fit is computed using
        the normal equations.

        The implementation intentionally avoids external numerical dependencies
        and solves the resulting 3x3 systems with the module's internal Gaussian
        elimination routine.

        Args:
            src: Sequence of source ``(x, y)`` coordinate pairs.
            dst: Sequence of corresponding destination ``(x, y)`` coordinate
                pairs.

        Returns:
            AffineTransform2D: Best-fit affine transformation mapping ``src`` to
            ``dst``.

        Raises:
            ValueError: If ``src`` and ``dst`` contain different numbers of
                points, fewer than three point pairs are supplied, or the
                calibration geometry is degenerate.
        """
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
