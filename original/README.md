# Historical C source layers

- `pristine/` is an unchanged copy of the July 23, 1998 source files.
- `modern-port/` applies mechanical compiler-portability changes only.
- `physics-fixes/` contains reviewable spin and initialization physics fixes.
- `instrumentation/` contains state-neutral reference export instrumentation.

Reference builds apply those layers in that order in disposable directories.
