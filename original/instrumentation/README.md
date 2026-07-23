# Corrected-C instrumentation

`0001-write-field-time-and-plate-velocity.patch` adds two binary
`float64` sidecars at each field frame:

- `<run>.fieldtime`: exact event time
- `<run>.platevel`: exact bottom-plate vertical velocity

Particle state, collision operators, event scheduling, and restart serialization
are unchanged. When the historical loop stops on the terminal plate event, the
patch writes the pending terminal statistics and field records at that same
timestamp; this supplies `32*N+1` frames without advancing beyond the requested
cycle. Interval collision counts are read from columns 15 through 17 of the
historical 26-column statistics records.

The reference generator applies this patch only after the portability and spin
patches, records its SHA-256 hash, and compares final restart files from small
corrected runs with and without this patch.
