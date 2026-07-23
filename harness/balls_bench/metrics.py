from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from balls_bench.cases import PHASES_PER_CYCLE
from balls_bench.trajectory import Trajectory


@dataclass(frozen=True)
class HeightMetrics:
    contrast: float
    dominant_wavelength: float
    q2: float
    q4: float
    q6: float


def top_height_field(
    positions: np.ndarray,
    diameters: np.ndarray,
    plate_z: float,
    box_width: float,
    grid_size: int = 100,
) -> np.ndarray:
    if positions.shape != (diameters.size, 3):
        raise ValueError("positions and diameters have incompatible shapes")
    if grid_size < 4:
        raise ValueError("grid_size must be at least 4")

    xy = np.clip(
        np.floor(positions[:, :2] * grid_size / box_width).astype(np.int64),
        0,
        grid_size - 1,
    )
    top = positions[:, 2] + diameters / 2.0 - plate_z
    field = np.full((grid_size, grid_size), -np.inf, dtype=np.float64)
    np.maximum.at(field, (xy[:, 1], xy[:, 0]), top)
    occupied = np.isfinite(field)
    if not np.any(occupied):
        raise ValueError("height field has no occupied cells")
    field[~occupied] = float(np.median(field[occupied]))
    return field


def height_metrics(
    field: np.ndarray,
    box_width: float,
    smoothing_sigma: float = 2.0,
) -> HeightMetrics:
    if field.ndim != 2 or field.shape[0] != field.shape[1]:
        raise ValueError("height field must be square")
    smoothed = gaussian_filter(
        np.asarray(field, dtype=np.float64),
        sigma=smoothing_sigma,
        mode="wrap",
    )
    contrast = float(np.std(smoothed))
    if contrast == 0:
        return HeightMetrics(0.0, 0.0, 0.0, 0.0, 0.0)

    standardized = (smoothed - np.mean(smoothed)) / contrast
    window = np.hanning(field.shape[0])
    spectrum = np.fft.fftshift(np.fft.fft2(standardized * np.outer(window, window)))
    power = np.abs(spectrum) ** 2

    spacing = box_width / field.shape[0]
    frequencies = np.fft.fftshift(np.fft.fftfreq(field.shape[0], d=spacing))
    kx, ky = np.meshgrid(frequencies, frequencies)
    radial_frequency = np.hypot(kx, ky)
    shell_width = 1.0 / box_width
    shell = np.rint(radial_frequency / shell_width).astype(np.int64)
    shell_power = np.bincount(shell.ravel(), weights=power.ravel())
    shell_power[:2] = 0.0
    peak_shell = int(np.argmax(shell_power))
    if peak_shell == 0 or shell_power[peak_shell] <= 0:
        return HeightMetrics(contrast, 0.0, 0.0, 0.0, 0.0)

    peak_frequency = peak_shell * shell_width
    annulus = np.abs(radial_frequency - peak_frequency) <= 0.75 * shell_width
    annulus_power = power[annulus]
    theta = np.arctan2(ky[annulus], kx[annulus])
    denominator = float(np.sum(annulus_power))

    def order(m: int) -> float:
        if denominator == 0:
            return 0.0
        return float(
            np.abs(np.sum(annulus_power * np.exp(1j * m * theta))) / denominator
        )

    return HeightMetrics(
        contrast=contrast,
        dominant_wavelength=1.0 / peak_frequency,
        q2=order(2),
        q4=order(4),
        q6=order(6),
    )


def order_parameter_profile(
    trajectory: Trajectory,
    box_width: float,
    grid_size: int = 100,
) -> dict[str, np.ndarray]:
    values = {
        "contrast": [],
        "dominant_wavelength": [],
        "q2": [],
        "q4": [],
        "q6": [],
    }
    for frame in range(trajectory.frame_count):
        field = top_height_field(
            trajectory.positions[frame],
            trajectory.diameters,
            float(trajectory.plate_z[frame]),
            box_width,
            grid_size,
        )
        result = height_metrics(field, box_width)
        values["contrast"].append(result.contrast)
        values["dominant_wavelength"].append(result.dominant_wavelength)
        values["q2"].append(result.q2)
        values["q4"].append(result.q4)
        values["q6"].append(result.q6)
    return {name: np.asarray(value) for name, value in values.items()}


def scalar_profiles(trajectory: Trajectory) -> dict[str, np.ndarray]:
    relative_z = trajectory.positions[:, :, 2] - trajectory.plate_z[:, None]
    velocity_squared = np.sum(trajectory.velocities**2, axis=2)
    spin_squared = np.sum(trajectory.angular_velocities**2, axis=2)
    diameter_squared = trajectory.diameters[None, :] ** 2
    return {
        "com_height": np.mean(relative_z, axis=1),
        "layer_depth": np.percentile(relative_z, 95, axis=1)
        - np.percentile(relative_z, 5, axis=1),
        "mean_velocity": np.mean(trajectory.velocities, axis=1),
        "rms_velocity": np.sqrt(np.mean(velocity_squared, axis=1)),
        "mean_spin": np.mean(trajectory.angular_velocities, axis=1),
        "rms_spin": np.sqrt(np.mean(spin_squared, axis=1)),
        "rotational_kinetic_energy": np.mean(
            0.05 * diameter_squared * spin_squared,
            axis=1,
        ),
    }


def phase_conditioned(
    profile: np.ndarray,
    phases_per_cycle: int = PHASES_PER_CYCLE,
) -> np.ndarray:
    value = np.asarray(profile)
    if value.shape[0] % phases_per_cycle == 1:
        value = value[:-1]
    if value.shape[0] % phases_per_cycle:
        raise ValueError("profile length is not a whole number of drive cycles")
    cycles = value.shape[0] // phases_per_cycle
    return value.reshape((cycles, phases_per_cycle, *value.shape[1:])).mean(axis=0)


def collision_rates(
    trajectory: Trajectory,
    phases_per_cycle: int = PHASES_PER_CYCLE,
) -> dict[str, np.ndarray]:
    counts = np.asarray(trajectory.collision_counts, dtype=np.float64)
    if counts.shape[0] % phases_per_cycle:
        raise ValueError("collision intervals do not span whole drive cycles")
    cycles = counts.shape[0] // phases_per_cycle
    total = counts.sum(axis=0) / (trajectory.particle_count * cycles)
    phase = counts.reshape(cycles, phases_per_cycle, 3).sum(axis=0)
    phase *= phases_per_cycle / (trajectory.particle_count * cycles)
    return {"total": total, "phase_conditioned": phase}


def profile_error(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if reference.shape != candidate.shape:
        raise ValueError(
            f"profile shapes differ: {reference.shape} versus {candidate.shape}"
        )
    difference = candidate - reference
    scale = float(np.std(reference))
    if scale < np.finfo(np.float64).eps:
        scale = max(float(np.sqrt(np.mean(reference**2))), 1.0)
    return {
        "mae": float(np.mean(np.abs(difference))),
        "rmse": float(np.sqrt(np.mean(difference**2))),
        "normalized_rmse": float(np.sqrt(np.mean(difference**2)) / scale),
    }
