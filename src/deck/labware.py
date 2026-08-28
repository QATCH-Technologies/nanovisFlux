from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..geometry.coordinates import DeckPoint


class WellShape(Enum):
    """Cross-sectional shape of a well."""

    CIRCULAR = "circular"
    RECTANGULAR = "rectangular"


class BottomShape(Enum):
    """Profile of the well's deepest point.

    The bottom profile affects the usable liquid volume and the amount of
    dead volume below the safe aspirate clearance, but does not directly
    affect motion planning.
    """

    FLAT = "flat"
    ROUND = "round"
    V = "v"


@dataclass(frozen=True)
class WellGeometry:
    """Describe the physical geometry shared by one or more wells.

    Defines the well shape, dimensions, depth, bottom profile, aspirate
    clearance, and nominal capacity. The geometry is normally shared by all
    wells in a labware, but individual wells may override it when required.

    ``depth_mm`` is measured from the well opening to its deepest point.
    ``bottom_clearance_mm`` defines the default vertical standoff maintained
    above the deepest point when resolving a well at ``"clearance"``.

    Args:
        shape: Cross-sectional shape of the well.
        diameter_mm: Diameter of a circular well in millimetres.
        width_mm: Width of a rectangular well in millimetres.
        length_mm: Length of a rectangular well in millimetres.
        depth_mm: Distance from the well opening to its deepest point.
        bottom: Profile of the well bottom.
        bottom_clearance_mm: Default clearance above the deepest point.
        max_volume_ul: Maximum nominal well volume in microlitres.
    """

    shape: WellShape = WellShape.CIRCULAR
    diameter_mm: float = 0.0  # circular wells
    width_mm: float = 0.0  # rectangular wells, x
    length_mm: float = 0.0  # rectangular wells, y
    depth_mm: float = 0.0
    bottom: BottomShape = BottomShape.FLAT
    bottom_clearance_mm: float = 1.0
    max_volume_ul: float = 0.0

    def z_delta(self, ref: str, clearance_mm: float | None = None) -> float:
        """Return the vertical offset from the well opening.

        Args:
            ref: Named vertical reference. Supported values are ``"top"``,
                ``"bottom"``, and ``"clearance"``.
            clearance_mm: Optional override for the configured bottom
                clearance when ``ref`` is ``"clearance"``.

        Returns:
            The deck-Z offset from the well opening in millimetres.

        Raises:
            ValueError: If ``ref`` is not a supported well reference.
        """
        if ref == "top":
            return 0.0
        if ref == "bottom":
            return -self.depth_mm
        if ref == "clearance":
            clr = self.bottom_clearance_mm if clearance_mm is None else clearance_mm
            return -max(0.0, self.depth_mm - clr)
        raise ValueError(f"unknown well reference {ref!r} (expected top/bottom/clearance)")


@dataclass
class Well:
    """Represent a named, addressable well within labware.

    The well offset identifies its centre relative to the labware origin,
    with Z referenced to the well opening. Bottom and clearance positions
    are derived from the associated :class:`WellGeometry` rather than being
    encoded directly in the well offset.

    Args:
        name: Address of the well, such as ``"A1"``.
        offset: Well-centre position relative to the labware origin.
        geometry: Physical geometry of the well.
    """

    name: str
    offset: DeckPoint
    geometry: WellGeometry = field(default_factory=WellGeometry)

    def at(self, ref: str = "top", clearance_mm: float | None = None) -> DeckPoint:
        """Return the well position at a specified vertical reference.

        Args:
            ref: Vertical reference within the well. Supported values are
                ``"top"``, ``"bottom"``, and ``"clearance"``.
            clearance_mm: Optional override for the configured bottom
                clearance.

        Returns:
            A deck-space point at the requested well reference.
        """
        return self.offset + DeckPoint(0, 0, self.geometry.z_delta(ref, clearance_mm))


_ROW_LETTERS = "ABCDEFGHIJKLMNOP"


@dataclass
class Labware:
    """Represent a placed or placeable collection of addressable wells.

    Labware can be constructed from a regular rectangular grid using
    :meth:`grid` or from explicit well definitions using :meth:`from_dict`.
    Wells may share a common geometry or provide individual geometry
    overrides.

    Once placed on a deck slot, :meth:`well` resolves a named well into an
    absolute deck-space coordinate. Grid row offsets are adjusted during
    placement to account for the slot's coordinate convention.

    Args:
        name: Name or identifier of the labware.
        brand: Optional vendor or manufacturer name.
        wells: Mapping of well names to :class:`Well` objects.
        slot: Deck slot on which the labware is placed, if any.
    """

    name: str
    brand: str = ""
    wells: dict = field(default_factory=dict)
    slot: object = None
    _pending_row_flip: bool = field(default=False, repr=False, compare=False)

    def place(self, slot) -> None:
        """Place the labware on a deck slot.

        Records the slot association and, for grid-generated labware, applies
        the deferred row-coordinate transformation required by the slot's
        coordinate frame.

        Args:
            slot: Deck slot on which the labware is placed.
        """
        self.slot = slot
        if self._pending_row_flip and slot.size and slot.size[1]:
            height = slot.size[1]
            for well in self.wells.values():
                well.offset = DeckPoint(well.offset.x, height - well.offset.y, well.offset.z)
            self._pending_row_flip = False

    def well(
        self,
        name: str,
        ref: str = "top",
        clearance_mm: float | None = None,
    ) -> DeckPoint:
        """Resolve a named well to an absolute deck-space position.

        Args:
            name: Well address, such as ``"A1"``.
            ref: Vertical reference within the well. Supported values are
                ``"top"``, ``"bottom"``, and ``"clearance"``.
            clearance_mm: Optional override for the well's configured
                bottom clearance.

        Returns:
            Absolute deck-space coordinate of the requested well position.

        Raises:
            RuntimeError: If the labware has not been placed on a deck slot.
            KeyError: If ``name`` is not an addressable well.
        """
        if self.slot is None:
            raise RuntimeError(f"labware {self.name!r} is not placed on the deck")
        return self.slot.origin + self.wells[name].at(ref, clearance_mm)  # type: ignore

    @classmethod
    def grid(
        cls,
        name: str,
        *,
        rows: int,
        cols: int,
        origin: DeckPoint,
        row_spacing_mm: float,
        col_spacing_mm: float,
        geometry: WellGeometry | None = None,
        brand: str = "",
    ) -> Labware:
        """Construct a uniformly spaced, conventionally named well grid.

        Wells are named row-major using alphabetic row identifiers and
        numeric column identifiers, such as ``A1``, ``A2``, and ``B1``.
        ``origin`` identifies the centre of A1 at the well opening.

        Args:
            name: Name or identifier for the resulting labware.
            rows: Number of well rows.
            cols: Number of well columns.
            origin: A1 centre relative to the labware origin.
            row_spacing_mm: Centre-to-centre spacing between rows.
            col_spacing_mm: Centre-to-centre spacing between columns.
            geometry: Geometry shared by all generated wells.
            brand: Optional vendor or manufacturer name.

        Returns:
            A new :class:`Labware` containing the generated well grid.
        """
        geometry = geometry or WellGeometry()
        wells = {}
        for r in range(rows):
            for c in range(cols):
                well_name = f"{_ROW_LETTERS[r]}{c + 1}"
                pos = DeckPoint(
                    origin.x + c * col_spacing_mm, origin.y + r * row_spacing_mm, origin.z
                )
                wells[well_name] = Well(well_name, pos, geometry)
        labware = cls(name=name, brand=brand, wells=wells)
        labware._pending_row_flip = True
        return labware

    @classmethod
    def from_dict(cls, data: dict) -> Labware:
        """Construct labware from a dictionary representation.

        The dictionary may describe either a regular ``grid`` or an explicit
        collection of wells. A default well geometry may be supplied at the
        labware level, with individual wells optionally overriding it.

        Args:
            data: Dictionary containing the labware name and optional brand,
                geometry, grid, or explicit well configuration.

        Returns:
            A new :class:`Labware` populated from ``data``.
        """
        default_geometry = _geometry_from_dict(data.get("well_geometry", {}))
        brand = data.get("brand", "")
        if "grid" in data:
            g = data["grid"]
            return cls.grid(
                name=data["name"],
                rows=g["rows"],
                cols=g["cols"],
                origin=DeckPoint(g["origin"]["x"], g["origin"]["y"], g["origin"].get("z", 0.0)),
                row_spacing_mm=g["row_spacing_mm"],
                col_spacing_mm=g["col_spacing_mm"],
                geometry=default_geometry,
                brand=brand,
            )
        wells = {}
        for n, o in data.get("wells", {}).items():
            offset = DeckPoint(o["x"], o["y"], o.get("z", 0.0))
            geometry = _geometry_from_dict(o["geometry"]) if "geometry" in o else default_geometry
            wells[n] = Well(n, offset, geometry)
        return cls(name=data["name"], brand=brand, wells=wells)


def _geometry_from_dict(d: dict) -> WellGeometry:
    """Construct well geometry from serialized configuration data.

    Missing fields use the defaults defined by :class:`WellGeometry`.

    Args:
        d: Dictionary containing serialized well geometry fields.

    Returns:
        A configured :class:`WellGeometry` instance.
    """
    if not d:
        return WellGeometry()
    return WellGeometry(
        shape=WellShape(d.get("shape", "circular")),
        diameter_mm=d.get("diameter_mm", 0.0),
        width_mm=d.get("width_mm", 0.0),
        length_mm=d.get("length_mm", 0.0),
        depth_mm=d.get("depth_mm", 0.0),
        bottom=BottomShape(d.get("bottom", "flat")),
        bottom_clearance_mm=d.get("bottom_clearance_mm", 1.0),
        max_volume_ul=d.get("max_volume_ul", 0.0),
    )
