# Mechanical modern-toolchain and memory-safety port

This tree starts from `../pristine` and contains only mechanical changes needed
to compile and execute the historical C/C++ sources safely on a modern system:

- replace `<iostream.h>` with `<iostream>` and import `std`
- give legacy procedures explicit `void` return types required by modern C++
- repair the `ParamStruct` tag declaration
- define the historical `PI` constant explicitly
- size the `loss` and `gain` arrays for the existing `ZGSIZE` initialization
  loop, eliminating a two-element global buffer overflow
- prevent `c_calc` from scheduling a collision against particle `-1` when no
  stationary-wall collision was found
- skip neighbor cells outside the allocated ghost-cell grid instead of reading
  past `TheGrid` at a nonperiodic boundary
- fail through the historical particle-escape reporter before a virtual-cell
  crossing can index outside the physical box
- declare legacy procedures as `void` instead of invoking undefined behavior
  by falling off the end of value-returning functions
- fail through the historical crash reporter when a root solver does not
  converge, and return the existing no-collision sentinel for non-spheres

`PORT_CHANGES.diff` is the reviewable source diff. Figure parameters, the spin
correction, and output instrumentation are intentionally absent from this tree.
