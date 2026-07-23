# Updated C references

Reference trajectories and checkpoints are too large for this repository. Set
an external artifact root before generating them. Reference generation requires
spin and sanitizer qualification reports for the current `Updated` source,
compiler, and machine. If those reports are absent, `reference-generate`
creates them automatically under `<artifact-root>/_gates/`.

To run the qualification explicitly before starting a long generation:

```sh
uv run balls-bench spin-gate --output /external/figure1/_gates/spin-gate.json
uv run balls-bench portability-gate \
  --output /external/figure1/_gates/portability-gate.json
```

Then generate and validate the reference collection:

```sh
uv run balls-bench reference-generate \
  --case all \
  --artifact-root /external/figure1
uv run balls-bench reference-collection \
  --artifact-root /external/figure1
uv run balls-bench validate-reference \
  /external/figure1/manifest.json \
  --load-trajectories
```

Each case manifest records the locked `original_1998` and `Updated` source
hashes; compiler version; spin and sanitizer gate reports; cycle selection;
trajectory/checkpoint hashes; retained run logs; and runtime.
Regenerable source trees and raw C field files are pruned after a trajectory
validates successfully. The accepted non-`e` settled cycles are `a=680`,
`b=2700`, `f=212`, and `cd/g/h=300`. Dense exports then cover four cycles for
`a/b/cd` and eight cycles for `f/g/h`. Panel `e` first requires the legacy
`findroot` assertion at `detect.c:840`, records its particle and
penetration diagnostic, and exports exactly the final four complete cycles
before that failure from the same uninterrupted 32-phase-per-cycle run. A
Python sidecar archives a rolling set of phase-zero restart files during that
run. Restarting `Updated` reconstructs its event queue and can move the
root-finder failure, so a restarted trajectory is not accepted as panel `e`
crash-window evidence.

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
state. The lock records the accepted cycle-300 checkpoints for `cd/g/h`;
populate them from externally retained artifacts or regenerate them before
dense export. Sparse completion-run archives are not evaluator inputs and are
not stored in Git.

The event scheduler inherited from the 1998 code can eventually encounter
position or time differences too small for double precision to order reliably.
A dense microconfiguration may then abort in `findroot` even though the
macroscopic pattern is seed-insensitive. For non-`e` cases, reference
generation may therefore resume from an exact phase-zero checkpoint. A
checkpoint before the canonical settled cycle is advanced with sparse output
to that cycle before dense trajectory export. Supply such a checkpoint
explicitly when needed:

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

`reference/manifests/provenance-lock.json` prevents reference generation after
an unreviewed source or physics change. `figure1-paper.json` records the
reproducible published-panel crop and order metrics.

The selected images under `reference/rendered/` were generated with `Updated`
and compared with Figure 1 of the 1998 paper. They reproduce the reported
square, stripe, hexagonal, and oscillatory pattern classes.

The challenge papers can be re-fetched with
`challenge/sources/retrieve.sh`; expected checksums are in
`challenge/sources/manifest.json`.
