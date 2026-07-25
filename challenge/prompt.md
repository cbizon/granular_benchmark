# Reproduce the granular-layer simulations in Bizon et al. Figure 1

The paper `sources/bizon1998a.pdf` describes comparison between a simulation
and experiment. Implement the simulation described there in Python and use
it to reproduce the simulation snapshots shown in Figure 1 of the paper.

Continue until you accurately reproduce the Figure 1 snapshots in pattern
and wavelength or conclude that you cannot. Decide for yourself how to validate
against the paper.

## Available software and references

The environment provides Python 3.12, `uv`, NumPy, SciPy, Numba, Matplotlib,
Pillow, psutil, pytest, and the Poppler PDF tools `pdftotext`, `pdfinfo`, and
`pdftoppm`. Code compiled through Python tools such as Numba is allowed.

You may read only the files in this workspace. The sources directory contains
several of the papers cited in bizon1998a. Do not look for another
implementation locally, online, or on GitHub. General network access is
unavailable.

## What to submit

You may organize and run your Python code however you choose. Submit:

1. Seven physics output files described below, one per simulation condition.
2. A manifest of those files at `submission/manifest.json`. The manifest must
   conform to `schema/submission.schema.json`.
3. A JSON run status conforming to `schema/final-response.schema.json`.

### Physics output files

Each output file must be an NPZ file readable with
`numpy.load(..., allow_pickle=False)`. It must contain exactly these numeric
arrays:

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

`N` is the particle count. The particle index must identify the same particle
in every frame.

Normalize the arrays using the mean particle diameter `D` and gravitational
acceleration `g`:

- length: `D`, with mean particle diameter equal to 1
- acceleration: `g`, with downward gravitational acceleration equal to 1

Use a right-handed coordinate system in which `z` increases upward. `positions`
and `plate_z` must use the same origin.

Export 4 forcing cycles for `a`, `b`, `cd`, and `e`, and 8 forcing cycles for
`f`, `g`, and `h`. Record 32 equal phase intervals per forcing cycle, including
the initial frame and the final endpoint, so:

```text
F = 32 * number_of_cycles + 1
```

At t=0 the plate is at the midpoint of its oscillation and moving upwards.
The first frame must have `drive_phase = 0`. The endpoint of every complete
forcing cycle must also have phase 0. `time` must be strictly increasing.

The columns of `collision_counts`, in order, are:

```text
ball_ball, stationary_wall, bottom_plate
```

Row `i` contains the number of collisions between frame `i` and frame `i+1`.

### Manifest contents

Paths in the manifest are relative to the directory containing the manifest.
Lengths in the manifest use the normalized length unit defined above.

Figure 1 contains seven independent simulation conditions. Use these manifest
keys:

- `a` for panel a
- `b` for panel b
- `cd` for the single simulation shown at two phases in panels c and d
- `e` for panel e
- `f` for panel f
- `g` for panel g
- `h` for panel h

For each manifest key, provide:

- `trajectory`: path to the trajectory NPZ file
- `particle_count`: number of particles
- `box_width`: box size in the x and y directions
- `box_height`: box size in the z direction
- `seed`: random seed used for the simulation
- `simulation_cycle`: total forcing cycles simulated from initialization
  through the final submitted trajectory frame
- `walltime_seconds`: elapsed wall-clock seconds for the simulation run that
  produced the submitted trajectory

### Run status format

The run-status JSON describes the outcome of the overall attempt. Provide:

- `status`: `complete`, `partial`, or `failed`
- `submission_manifest`: path to the submission manifest
- `cases_complete`: manifest keys for the completed simulation conditions
- `limitations`: a list of incomplete work, known problems, or other
  qualifications
