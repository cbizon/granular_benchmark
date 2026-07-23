# Granular Figure 1 benchmark

Provider-neutral benchmark for testing whether a coding agent can independently
reproduce Figure 1 from:

C. Bizon, M. D. Shattuck, J. B. Swift, W. D. McCormick, and H. L. Swinney,
"Patterns in 3D Vertically Oscillated Granular Layers: Simulation and
Experiment," *Physical Review Letters* 80, 57-60 (1998).

The repository contains the challenge presented to the agent, trusted
evaluation code, corrected-C reference generation and validation tools,
container isolation, and a durable RENCI Sterling Kubernetes runner. It
intentionally does **not** contain the earlier `balls_56_independent` Python
implementation or its development outputs.

## Repository layout

- `challenge/`: prompt, cases, source papers, schemas, and Python starter
- `harness/`: staging, provider adapters, metrics, evaluation, containers, and
  Sterling orchestration
- `harness_tests/`: unit and integration-oriented harness tests
- `original/`: historical C source, mechanical port, reviewed physics fixes,
  and state-neutral instrumentation used to build references
- `reference/manifests/`: locked case, source, checkpoint, and paper metadata
- `reference/rendered/`: selected corrected-C reference images
- `reference/generated-300/`: validated cycle-300 completion archive

The large phase-dense trajectories and local settled-checkpoint cache are not
stored in Git. Their hashes, accepted cycles, and generation procedures are
committed under `reference/`.

## Setup

Python 3.12 and `uv` are required:

```sh
uv sync --all-groups
uv run pytest
```

Fast reference gates:

```sh
uv run balls-bench spin-gate --output artifacts/spin-gate.json
uv run balls-bench portability-gate \
  --output artifacts/portability-gate.json
uv run balls-bench verify-instrumentation \
  --output artifacts/instrumentation-transparency.json
uv run balls-bench validate-sources
```

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
historical C source, benchmark harness, trusted references, prior submissions,
or any excluded Python implementation.

## Metrics

Evaluation compares reference and candidate trajectories, paper-level pattern
features, physical totals, time profiles, performance, and the prevalence and
severity of non-physical particle overlaps. Definitions are in
[`harness/METRICS.md`](harness/METRICS.md).

## Reference data

The committed cycle-300 archive is approximately 37 MB and contains exact
restart files, cumulative statistics, logs, statuses, and provenance manifests
for the six non-`e` cases. Some manifests retain absolute temporary paths from
the original executions. Those strings are historical provenance, are covered
by recorded artifact hashes, and are not runtime requirements.

The canonical dense references use settled cycles `a=680`, `b=2700`, `f=212`,
and `cd/g/h=300`, plus the uninterrupted panel `e` crash window. See
[`reference/README.md`](reference/README.md) for generation and validation.
