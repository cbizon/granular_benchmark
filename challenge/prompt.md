# Figure 1 simulation challenge

Build an independent Python 3.12 implementation of the event-driven granular
simulation described in the supplied papers and reproduce the seven independent
Figure 1 cases `a`, `b`, `cd`, `e`, `f`, `g`, and `h`.

You may read only this workspace. You have no access to any historical,
corrected, archived, reference, local, or online implementation. Do not attempt
to locate another implementation. General network access is unavailable.

## Environment

The locked environment provides Python 3.12, `uv`, NumPy, SciPy, Numba,
Matplotlib, Pillow, psutil, and pytest. Implement the simulator in Python.
Compiled acceleration produced from Python tooling, including Numba, is allowed.

The source papers are in `sources/`. `cases.json` is authoritative for the seven
parameter points. The paper's frequency is
`f_star = f * sqrt(H/g)`. Exported trajectories use `D=1`, `g=1`, velocity
`sqrt(gD)`, and time `sqrt(D/g)`, so the drive frequency in exported time units
is `f_star / sqrt(5.42)`.

## Required commands

Keep the entry point at `benchmark.py`.

```text
python benchmark.py export \
  --case CASE \
  --checkpoint CHECKPOINT \
  --output OUTPUT

python benchmark.py advance \
  --case CASE \
  --checkpoint CHECKPOINT \
  --cycles 1 \
  --output OUTPUT_CHECKPOINT
```

`export` must start from the phase-zero settled checkpoint and write the full
required trajectory. It must write 4 drive cycles for the `f/2` cases
`a,b,cd,e` and 8 drive cycles for the `f/4` cases `f,g,h`, always at 32 equal
phase intervals per drive cycle including both endpoints.

`advance` must load the supplied checkpoint, advance by exactly the requested
integer number of drive cycles, and write a new checkpoint. The harness invokes
one warm-up and three timed one-cycle repetitions.

## Trajectory format

Each trajectory is an NPZ readable with `numpy.load(..., allow_pickle=False)`.
It must contain exactly these named numeric arrays:

```text
time                  (F,)       float
drive_phase           (F,)       float in [0,1)
positions             (F,N,3)    float
velocities            (F,N,3)    float
angular_velocities    (F,N,3)    float
diameters             (N,)       float
plate_z               (F,)       float
plate_vz              (F,)       float
collision_counts      (F-1,3)    nonnegative integer
```

`F = 32 * export_cycles + 1`, `N = 60000`, and phase zero is the first and last
frame of each drive cycle. Collision columns are, in order, `ball_ball`,
`stationary_wall`, and `bottom_plate`. Counts cover the interval from frame `i`
to frame `i+1`.

## Submission

Write `submission/manifest.json` conforming to
`schema/submission.schema.json`. Every case needs a phase-zero settled
checkpoint, trajectory, particle count, normalized box width and height, seed,
and settled cycle. Paths are relative to the manifest.

Do not report precomputed metrics. The harness recalculates order parameters,
dynamics, overlaps, and collision rates from the arrays. Do not special-case the
evaluator or fabricate output.

Your final response must be JSON conforming to
`schema/final-response.schema.json`.
