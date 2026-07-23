# Corrected-C references

Reference trajectories and checkpoints are too large for this repository. Set
an external artifact root and generate each case only after the fast gates:

```sh
uv run balls-bench spin-gate --output /external/figure1/_gates/spin-gate.json
uv run balls-bench portability-gate \
  --output /external/figure1/_gates/portability-gate.json
uv run balls-bench reference-generate \
  --case all \
  --artifact-root /external/figure1
uv run balls-bench reference-collection \
  --artifact-root /external/figure1
uv run balls-bench validate-reference \
  /external/figure1/manifest.json \
  --load-trajectories
```

Each case manifest records pristine, portability, spin-fix, initial-velocity,
and instrumentation hashes; compiler version; spin, sanitizer, and
instrumentation gate reports; cycle selection; trajectory/checkpoint hashes;
retained run logs; and runtime.
Regenerable source trees and raw C field files are pruned after a trajectory
validates successfully. The accepted non-`e` settled cycles are `a=680`,
`b=2700`, `f=212`, and `cd/g/h=300`. Dense exports then cover four cycles for
`a/b/cd` and eight cycles for `f/g/h`. Panel `e` first requires the
historical `findroot` assertion at `detect.c:840`, records its particle and
penetration diagnostic, and exports exactly the final four complete cycles
before that failure from the same uninterrupted 32-phase-per-cycle run. A
Python sidecar archives a rolling set of phase-zero restart files during that
run. Restarting the historical code reconstructs its event queue and can move
the root-finder failure, so a restarted trajectory is not accepted as panel
`e` crash-window evidence.

`reference/manifests/cases.json` fixes parameters and normalization.
It also records the selected reference seed for each case. These seeds do not
define the physics: they are microconfigurations known to avoid, or permit
checkpoint traversal around, rare double-precision event-ordering failures in
dense states. The selected seeds are `a=1825001`, `b=16538`, `cd=16533`,
`e=16532`, `f=590018`, `g=16533`, and `h=16533`.

`reference/manifests/settled-checkpoints.json` locks the exact accepted
checkpoint cycle, byte count, and SHA-256 for every non-`e` case. Populate the
ignored local cache under `reference/settled-checkpoints/`, or pass a
checkpoint explicitly. Reference generation verifies that the state at the
canonical settled cycle matches the lock before dense export starts. Panel
`a` uses the accepted cycle-680 square state and panel `b` uses the accepted
cycle-2700 stripe state. Panel `f` uses its audited dense-compatible cycle-212
state. The cycle-300 archive supplies `cd/g/h` and separately proves that the
selected `f` lineage completed 300 cycles.

The historical event scheduler can eventually encounter position or time
differences too small for double precision to order reliably. A dense
microconfiguration may then abort in `findroot` even though the macroscopic
pattern is seed-insensitive. For non-`e` cases, reference generation may
therefore resume from an exact phase-zero checkpoint. A checkpoint before the
canonical settled cycle is advanced with sparse output to that cycle before
dense trajectory export. Supply such a checkpoint explicitly when needed:

```sh
uv run balls-bench reference-generate \
  --case f \
  --artifact-root /external/figure1 \
  --equilibration-checkpoint /external/checkpoints/f-cycle-212.restart
```

The generated manifest records the input checkpoint cycle and hash, and labels
whether it was used directly or resumed to the canonical settled cycle. Panel
`e` is different: its uninterrupted assertion is part of the reference
selection, so checkpoint-based generation is rejected for that case.

If dense 32-phase output itself encounters an event-ordering barrier, additional
verified phase-zero states from the same selected lineage may divide the export
into explicit legs:

```sh
uv run balls-bench reference-generate \
  --case f \
  --artifact-root /external/figure1 \
  --equilibration-checkpoint /external/checkpoints/f-cycle-212.restart \
  --export-bridge-checkpoint /external/checkpoints/f-cycle-213.restart \
  --export-bridge-checkpoint /external/checkpoints/f-cycle-216.restart
```

Each leg is continuous. The manifest records every bridge cycle and checkpoint
hash so evaluators can distinguish this numerical workaround from the physical
model.

## Cycle-300 completion archive

`reference/generated-300/` contains strictly validated phase-zero checkpoints,
cumulative statistics, run logs, and provenance manifests for all six non-`e`
cases. Its collection manifest has `complete: true` for:

| Case | Seed |
| --- | ---: |
| `a` | 1825001 |
| `b` | 16538 |
| `cd` | 16533 |
| `f` | 590018 |
| `g` | 16533 |
| `h` | 16533 |

Every archived run has a successful status, an exact 6,480,064-byte restart
whose header is at cycle 300 within `1e-8`, and at least 301 complete 104-byte
statistics records. The `f` manifest records the exact-checkpoint restart chain
needed to traverse historical event-ordering failures and reach cycle 300.

This archive proves completion of the long corrected-C runs and supplies the
canonical settled checkpoints for `cd/g/h`. It is not the phase-dense
trajectory export used for benchmark profile comparison. Panel `f` instead
uses its audited cycle-212 dense trajectory; its cycle-300 archive remains
completion evidence. Longer annealing selected cycle 680 for `a` and cycle
2700 for `b`; cycle 3000 for `b` is retained only as a diagnostic endpoint.

`reference/manifests/provenance-lock.json` prevents reference generation after
an unreviewed source or physics change. `figure1-paper.json` records the
reproducible published-panel crop and order metrics.

The challenge papers can be re-fetched with
`challenge/sources/retrieve.sh`; expected checksums are in
`challenge/sources/manifest.json`.
