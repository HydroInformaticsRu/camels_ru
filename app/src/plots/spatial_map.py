from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    import folium
except ImportError:  # pragma: no cover
    folium = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    import geopandas as gpd
except ImportError:  # pragma: no cover
    gpd = None  # type: ignore[assignment]

_logger = logging.getLogger("app.plots.spatial_map")


def _ensure_latlon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame in EPSG:4326 with string gauge_id."""
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf.copy()
    if "gauge_id" in gdf.columns:
        gdf["gauge_id"] = gdf["gauge_id"].astype(str)
    return gdf


@lru_cache(maxsize=1)
def _load_gauge_data(path_str: str) -> gpd.GeoDataFrame:
    path = Path(path_str)
    gdf = gpd.read_file(path)
    return _ensure_latlon(gdf)


@lru_cache(maxsize=1)
def _load_watershed_data(path_str: str) -> gpd.GeoDataFrame:
    path = Path(path_str)
    gdf = gpd.read_file(path)
    return _ensure_latlon(gdf)


def _extract_point_latlon(point: Any) -> tuple[float, float]:
    return float(getattr(point, "y", 0.0)), float(getattr(point, "x", 0.0))


def _estimate_zoom_level(max_span: float) -> int:
    """Return a rough Leaflet zoom level for a geographic span in degrees."""
    if max_span <= 0:
        return 10
    thresholds = [
        (20.0, 5),
        (8.0, 6),
        (4.0, 7),
        (2.0, 8),
        (1.0, 9),
        (0.5, 10),
        (0.25, 11),
        (0.12, 12),
        (0.06, 13),
        (0.03, 14),
    ]
    for span, zoom in thresholds:
        if max_span >= span:
            return zoom
    return 15


def _symmetric_bounds(
    centroid_latlon: tuple[float, float],
    bounds: tuple[tuple[float, float], tuple[float, float]],
    padding_factor: float = 1.1,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return bounds expanded symmetrically around a centroid."""
    (south, west), (north, east) = bounds
    center_lat, center_lon = centroid_latlon

    lat_offset = max(center_lat - south, north - center_lat, 0.0)
    lon_offset = max(center_lon - west, east - center_lon, 0.0)

    min_offset = 0.01
    lat_offset = max(lat_offset, min_offset) * padding_factor
    lon_offset = max(lon_offset, min_offset) * padding_factor

    new_south = max(-90.0, center_lat - lat_offset)
    new_north = min(90.0, center_lat + lat_offset)
    new_west = max(-180.0, center_lon - lon_offset)
    new_east = min(180.0, center_lon + lon_offset)

    return (new_south, new_west), (new_north, new_east)


@dataclass(frozen=True)
class SpatialMapRender:
    html: str
    watershed_name: str | None = None
    watershed_area: float | None = None


def render_spatial_map_html(
    gauge_id: str,
    gauge_path: Path,
    watershed_path: Path,
    logger: logging.Logger | None = None,
) -> SpatialMapRender:
    """Render a Folium map showing the gauge point and watershed polygon."""
    log = logger or _logger

    if folium is None or gpd is None:
        log.warning(
            "Folium/GeoPandas not installed; skipping spatial map rendering"
        )
        return SpatialMapRender(html="")

    if not gauge_path.exists() or not watershed_path.exists():
        log.warning(
            "Spatial data not available; gauge_path=%s; watershed_path=%s",
            gauge_path,
            watershed_path,
        )
        return SpatialMapRender(html="")

    try:
        gauges = _load_gauge_data(str(gauge_path))
        watersheds = _load_watershed_data(str(watershed_path))
    except Exception:  # noqa: BLE001
        log.exception("Failed to load spatial data")
        return SpatialMapRender(html="")

    gauge = gauges[gauges["gauge_id"] == str(gauge_id)]
    watershed = watersheds[watersheds["gauge_id"] == str(gauge_id)]
    log.debug(
        "Spatial features located for gauge_id=%s (points=%s, polygons=%s)",
        gauge_id,
        len(gauge),
        len(watershed),
    )

    if gauge.empty and watershed.empty:
        log.warning("No spatial features found for gauge_id=%s", gauge_id)
        return SpatialMapRender(html="")

    gauge_latlon: tuple[float, float] | None = None
    centroid_latlon: tuple[float, float] | None = None
    watershed_geom = None
    watershed_name: str | None = None
    watershed_area: float | None = None

    if not gauge.empty:
        point_geom = gauge.geometry.iloc[0]
        gauge_latlon = _extract_point_latlon(point_geom)

    if not watershed.empty:
        watershed_geom = watershed.geometry.unary_union
        centroid = watershed_geom.centroid
        centroid_latlon = _extract_point_latlon(centroid)
        row = watershed.iloc[0]
        name = row.get("name_en") or row.get("name")
        if isinstance(name, str) and name.strip():
            watershed_name = name.strip()
        area_value = row.get("area")
        try:
            watershed_area = (
                float(area_value) if area_value is not None else None
            )
        except (TypeError, ValueError):
            watershed_area = None

    center_lat, center_lon = centroid_latlon or gauge_latlon or (0.0, 0.0)

    zoom_level = 8
    bounds: tuple[tuple[float, float], tuple[float, float]] | None = None
    if watershed_geom is not None:
        minx, miny, maxx, maxy = watershed_geom.bounds
        raw_bounds = ((miny, minx), (maxy, maxx))
        if centroid_latlon is not None:
            bounds = _symmetric_bounds(centroid_latlon, raw_bounds)
        else:
            bounds = raw_bounds
    elif gauge_latlon is not None:
        lat, lon = gauge_latlon
        bounds = ((lat - 0.05, lon - 0.05), (lat + 0.05, lon + 0.05))

    if bounds is not None:
        (south, west), (north, east) = bounds
        min_span = 0.005
        if (north - south) < min_span:
            center_lat = (north + south) / 2
            south = center_lat - min_span / 2
            north = center_lat + min_span / 2
        if (east - west) < min_span:
            center_lon = (east + west) / 2
            west = center_lon - min_span / 2
            east = center_lon + min_span / 2
        south = max(-90.0, south)
        north = min(90.0, north)
        west = max(-180.0, west)
        east = min(180.0, east)
        bounds = ((south, west), (north, east))
        lat_span = north - south
        lon_span = east - west
        zoom_level = _estimate_zoom_level(max(lat_span, lon_span))

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
        tiles="OpenStreetMap",
        control_scale=True,
        width="100%",
        height="100%",
    )

    if not watershed.empty:
        folium.GeoJson(
            data=json.loads(watershed.to_json()),
            name="Watershed",
            style_function=lambda _: {
                "color": "#2563eb",
                "weight": 2,
                "fillColor": "#93c5fd",
                "fillOpacity": 0.35,
            },
            highlight_function=lambda _: {
                "weight": 3,
                "color": "#1d4ed8",
                "fillOpacity": 0.45,
            },
        ).add_to(fmap)

    if gauge_latlon is not None:
        popup_value = gauge.iloc[0].get("name_en") or gauge.iloc[0].get(
            "name_ru"
        )
        folium.CircleMarker(
            location=list(gauge_latlon),
            radius=7,
            color="#ef4444",
            fill=True,
            fill_color="#ef4444",
            fill_opacity=0.9,
            popup=str(popup_value or gauge_id),
        ).add_to(fmap)

    if bounds is not None:
        try:
            (south, west), (north, east) = bounds
            fmap.fit_bounds([[south, west], [north, east]])
        except Exception:  # noqa: BLE001
            log.debug(
                "Failed to fit map bounds for gauge_id=%s",
                gauge_id,
                exc_info=True,
            )

    return SpatialMapRender(
        html=fmap._repr_html_(),
        watershed_name=watershed_name,
        watershed_area=watershed_area,
    )
