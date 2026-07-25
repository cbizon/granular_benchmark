# Updated reference simulator

This is the complete C source tree used by the benchmark's reference generator
and C validation tests. It is derived from `../original_1998` and already
contains the portability, safety, physics, initialization, and reference-output
updates described in `../README.md`.

The harness copies this directory directly into a run workspace, writes the
selected Figure 1 parameters and random seed into the copied headers, compiles
it, and runs it. No patches are applied during that process.

`spin_probe.cc` is a validation helper and is not part of the simulator
executable. The production source list is defined by
`harness/balls_bench/historical.py`.
