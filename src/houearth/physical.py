from __future__ import annotations

import math

import numpy as np


def _validate_limb_darkening(u1: float, u2: float) -> None:
    if u1 < 0 or u1 + u2 >= 1 or u1 + 2.0 * u2 < 0:
        raise ValueError("quadratic limb-darkening coefficients are not physical")


def circle_overlap_area(separation: np.ndarray, radius_ratio: float) -> np.ndarray:
    """Area shared by a unit stellar disk and a planet disk.

    The planet radius is expressed in stellar-radius units. The implementation is
    vectorized and exact for two uniform disks; limb darkening is applied separately.
    """
    if not 0 < radius_ratio < 1:
        raise ValueError("radius_ratio must be in (0, 1)")

    z = np.asarray(separation, dtype=float)
    area = np.zeros_like(z)
    full = z <= 1.0 - radius_ratio
    area[full] = math.pi * radius_ratio * radius_ratio

    partial = (z > 1.0 - radius_ratio) & (z < 1.0 + radius_ratio)
    if np.any(partial):
        zp = z[partial]
        r = radius_ratio
        planet_angle = np.arccos(
            np.clip((zp * zp + r * r - 1.0) / (2.0 * zp * r), -1.0, 1.0)
        )
        star_angle = np.arccos(
            np.clip((zp * zp + 1.0 - r * r) / (2.0 * zp), -1.0, 1.0)
        )
        radical = np.maximum(
            0.0,
            (-zp + r + 1.0)
            * (zp + r - 1.0)
            * (zp - r + 1.0)
            * (zp + r + 1.0),
        )
        area[partial] = r * r * planet_angle + star_angle - 0.5 * np.sqrt(radical)
    return area


def quadratic_intensity(mu: np.ndarray, u1: float, u2: float) -> np.ndarray:
    _validate_limb_darkening(u1, u2)
    mu = np.clip(np.asarray(mu, dtype=float), 0.0, 1.0)
    one_minus_mu = 1.0 - mu
    return 1.0 - u1 * one_minus_mu - u2 * one_minus_mu * one_minus_mu


def physical_single_transit_decrement(
    time: np.ndarray,
    *,
    center: float,
    duration: float,
    radius_ratio: float,
    impact_parameter: float = 0.3,
    u1: float = 0.35,
    u2: float = 0.25,
) -> np.ndarray:
    """Approximate a quadratic-limb-darkened single transit.

    ``duration`` is first-to-fourth contact duration. The overlap geometry is exact;
    the occulted intensity is evaluated at the planet-center position, which is a
    controlled small-planet approximation suitable for injection/recovery tests.
    """
    if duration <= 0:
        raise ValueError("duration must be positive")
    if not 0 <= impact_parameter < 1.0 + radius_ratio:
        raise ValueError("impact_parameter must permit a transit")
    _validate_limb_darkening(u1, u2)

    time = np.asarray(time, dtype=float)
    chord_half = math.sqrt(max((1.0 + radius_ratio) ** 2 - impact_parameter**2, 0.0))
    chord_position = 2.0 * chord_half * (time - center) / duration
    separation = np.sqrt(impact_parameter**2 + chord_position**2)
    overlap = circle_overlap_area(separation, radius_ratio) / math.pi

    projected_radius = np.minimum(separation, 1.0)
    mu = np.sqrt(np.maximum(0.0, 1.0 - projected_radius * projected_radius))
    local_intensity = quadratic_intensity(mu, u1, u2)
    disk_mean_intensity = 1.0 - u1 / 3.0 - u2 / 6.0
    return overlap * local_intensity / disk_mean_intensity


def radius_ratio_for_midpoint_depth(
    depth: float,
    *,
    impact_parameter: float = 0.3,
    u1: float = 0.35,
    u2: float = 0.25,
) -> float:
    """Invert the approximate model so its midpoint depth matches ``depth``."""
    if not 0 < depth < 0.25:
        raise ValueError("depth must be in (0, 0.25)")
    _validate_limb_darkening(u1, u2)
    probe_time = np.array([0.0])
    low, high = 1e-6, 0.5
    for _ in range(60):
        middle = 0.5 * (low + high)
        value = float(
            physical_single_transit_decrement(
                probe_time,
                center=0.0,
                duration=1.0,
                radius_ratio=middle,
                impact_parameter=impact_parameter,
                u1=u1,
                u2=u2,
            )[0]
        )
        if value < depth:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def inject_physical_single_transit(
    time: np.ndarray,
    flux: np.ndarray,
    *,
    center: float,
    duration: float,
    depth: float,
    impact_parameter: float = 0.3,
    u1: float = 0.35,
    u2: float = 0.25,
) -> tuple[np.ndarray, float]:
    """Inject a physical single transit and return flux plus inferred radius ratio."""
    radius_ratio = radius_ratio_for_midpoint_depth(
        depth,
        impact_parameter=impact_parameter,
        u1=u1,
        u2=u2,
    )
    decrement = physical_single_transit_decrement(
        time,
        center=center,
        duration=duration,
        radius_ratio=radius_ratio,
        impact_parameter=impact_parameter,
        u1=u1,
        u2=u2,
    )
    return np.asarray(flux, dtype=float) - decrement, radius_ratio
