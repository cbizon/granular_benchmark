# C source trees

This directory contains two complete source trees:

- `original_1998/` is an unchanged copy of the July 23, 1998 source release.
- `Updated/` is the ready-to-build source used by all reference-generation and
  C-validation commands in this benchmark.

`Updated` differs from `original_1998` in four areas:

1. It compiles with a modern C++ toolchain and repairs unsafe array bounds,
   invalid grid access, legacy return types, and other undefined behavior.
2. It corrects the bottom-plate rotational contact-vector sign. The benchmark
   spin gate checks the resulting collision operator against an independent
   Walton-model calculation.
3. It initializes fresh-run vertical velocities uniformly in
   `[-0.05, 0.05)` before the existing zero-momentum correction, removing the
   original drive-amplitude bias.
4. It writes exact field timestamps and bottom-plate velocities and emits the
   terminal statistics and field frame required for phase-resolved evaluation.

The benchmark copies `Updated` directly into each run directory. No source
patches are applied at runtime. The compiled tree passes the sanitizer and spin
gates, and its outputs were compared with Figure 1 of the 1998 paper. It
reproduces the square, stripe, hexagonal, and oscillatory pattern classes shown
there.
