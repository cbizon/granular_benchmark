# Evaluation definitions

All metrics are recalculated from submitted NPZ arrays.

## Height and symmetry

For each frame, the horizontal box is divided into a `100 x 100` grid. Each
cell receives the maximum particle top surface height, `z + D/2 - plate_z`.
Empty cells receive the median occupied height. The field is Gaussian-smoothed
with `sigma=2` cells.

- `contrast`: standard deviation of the smoothed height field
- `dominant_wavelength`: inverse frequency of the strongest nonzero radial
  Fourier shell after mean removal and a 2D Hann window
- `Qm`: magnitude of the Fourier-power-weighted `exp(i*m*theta)` average in the
  dominant shell, for `m=2,4,6`

The same crop and Fourier procedure is applied to the published simulation
panels. Paper-image contrast is reported but is not treated as a calibrated
height.

## Dynamics

- `COM height`: mean particle-center height relative to the plate
- `layer depth`: 95th minus 5th percentile of relative center height
- `mean velocity` and `mean spin`: componentwise particle means
- `RMS velocity` and `RMS spin`: root mean square vector magnitude
- `rotational kinetic energy`: particle mean of
  `0.05 * diameter^2 * |omega|^2`

Candidate profiles may be shifted only by an integer number of drive cycles
less than the expected temporal period. No fractional-cycle or arbitrary frame
alignment is allowed.

## Overlaps and collisions

Signed gap is surface separation. Counts are reported for gaps below
`0`, `-1e-6 D`, `-1e-5 D`, and `-1e-4 D`.

- `ball_ball`: unique particle pairs
- `stationary_wall`: each penetrated side or top wall surface
- `bottom_plate`: particles penetrating the moving plate

The evaluation viewer plots both the total count over all exported frames and
the 32-bin phase-conditioned mean frame count for each threshold and surface.
Candidate overlap profiles use the same integer-cycle alignment selected from
the scalar dynamics.

Collision totals are divided by particle count and exported drive cycles.
Each 32-bin phase rate is additionally multiplied by 32, so the mean of the
phase bins equals the total rate per particle per drive cycle.

Each submitted case reports `walltime_seconds` for the simulation run that
produced its trajectory. The harness also records total agent elapsed time
independently and uses that measurement in Global stats. Simulation runtime,
agent elapsed time, physics fidelity, and token usage are reported separately.
No composite score is calculated.
