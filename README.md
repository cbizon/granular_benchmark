# Granular Figure 1 benchmark

Provider-neutral benchmark for testing whether a coding agent can independently
reproduce Figure 1 from:

C. Bizon, M. D. Shattuck, J. B. Swift, W. D. McCormick, and H. L. Swinney,
"Patterns in 3D Vertically Oscillated Granular Layers: Simulation and
Experiment," *Physical Review Letters* 80, 57-60 (1998).

The repository contains the challenge presented to the agent, trusted
evaluation code, Updated C reference generation and validation tools,
container isolation, and a durable RENCI Sterling Kubernetes runner. It
intentionally does **not** contain the earlier `balls_56_independent` Python
implementation or its development outputs.

## Repository layout

- `challenge/`: prompt, cases, source papers, schemas, and Python starter
- `harness/`: staging, provider adapters, metrics, evaluation, containers, and
  Sterling orchestration
- `harness_tests/`: unit and integration-oriented harness tests
- `original/original_1998/`: unchanged source released with the 1998 paper
- `original/Updated/`: complete, ready-to-build C source used by the reference
  generator and C validation tests
- `reference/manifests/`: locked case, source, checkpoint, and paper metadata
- `reference/rendered/`: selected Updated C reference images

The large phase-dense trajectories, settled-checkpoint cache, and sparse
completion-run archives are not stored in Git. Their hashes, accepted cycles,
and generation procedures are committed under `reference/`.

## Setup

Python 3.12 and `uv` are required:

```sh
uv sync --all-groups
uv run pytest
```

## Reference-generation checks

These checks are for maintainers creating or regenerating trusted reference
data. They are not required to run a model trial. `uv run pytest` already runs
reduced versions against small particle counts so ordinary development catches
source, compilation, and physics regressions quickly.

The standalone commands qualify the exact `Updated` source, compiler, and
machine that will produce a reference:

- `spin-gate` compares the bottom-plate collision operator with an independent
  Walton-model calculation.
- `portability-gate` compiles with AddressSanitizer and
  UndefinedBehaviorSanitizer and runs the full 60,000-particle panel `f`
  configuration for two cycles.
- `validate-sources` verifies the hashes of the papers and other challenge
  source documents.

```sh
uv run balls-bench spin-gate --output artifacts/spin-gate.json
uv run balls-bench portability-gate \
  --output artifacts/portability-gate.json
uv run balls-bench validate-sources
```

The first two commands write auditable JSON reports containing `passed`, source
hashes, and check-specific details. The portability report also records the
compiler, completed cycles, return code, and run-log location. On failure, the
command exits nonzero and prints the reason. Spin failures leave per-case
expected and observed values in `spin-gate.json`; sanitizer or runtime failures
identify the portability run log. A compile failure prints the compiler output
directly. Source validation fails with the file whose checksum differs.

`reference-generate` creates missing spin and portability reports automatically
under the selected artifact root. Running these commands separately is useful
when changing `Updated` or diagnosing a reference-generation environment before
starting a long run.

## C source

The repository contains two concrete C source trees. `original_1998` preserves
the July 23, 1998 release unchanged. `Updated` is the version used by the
benchmark's reference-generation and C-validation tools; the harness copies
that directory directly and does not apply patches at runtime.

Relative to `original_1998`, `Updated`:

- builds with a modern C++ toolchain and fixes unsafe memory access and legacy
  undefined behavior
- corrects the bottom-plate rotational contact-vector sign
- removes drive-amplitude bias from fresh-run vertical velocities while
  preserving zero total vertical momentum
- records exact field times and plate velocities needed by the evaluator

Outputs from `Updated` were compared with Figure 1 of the 1998 paper and
reproduce its square, stripe, hexagonal, and oscillatory pattern classes.
Detailed source and validation notes are in
[`original/README.md`](original/README.md).

## Run on Sterling

After one-time image configuration, a complete trial is one command:

```sh
uv run balls-sterling run --model MODEL
```

That command chains cluster setup checks, provider selection, agent execution,
trusted evaluation, SHA-256-verified artifact retrieval, result validation, and
cleanup. The Kubernetes pipeline continues if the terminal, laptop, VPN, or
provider client connection disappears. Running the same command again resumes
the active trial.

See
[`harness/kubernetes/sterling/README.md`](harness/kubernetes/sterling/README.md)
for image configuration, isolation, and recovery details.

## Local trial workflow

The lower-level local workflow remains available for development:

```sh
uv run balls-bench trial-create tests \
  --provider codex \
  --model MODEL \
  --test-id TEST_ID

uv run balls-bench trial-run tests/TEST_ID

uv run balls-bench trial-evaluate \
  tests/TEST_ID \
  /external/figure1/manifest.json
```

The agent workspace contains only the staged challenge. It does not contain the
two C source trees, benchmark harness, trusted references, prior submissions,
or any excluded Python implementation.

## Metrics

Evaluation compares reference and candidate trajectories, paper-level pattern
features, physical totals, time profiles, performance, and the prevalence and
severity of non-physical particle overlaps. Definitions are in
[`harness/METRICS.md`](harness/METRICS.md).

## Reference data

The canonical dense references use settled cycles `a=680`, `b=2700`, `f=212`,
and `cd/g/h=300`, plus the uninterrupted panel `e` crash window. See
[`reference/README.md`](reference/README.md) for generation and validation.
