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

- `challenge/`: prompt, internal case definitions, source papers, schemas, and
  the minimal Python environment scaffold
- `harness/`: staging, provider adapters, metrics, evaluation, containers, and
  Sterling orchestration
- `harness_tests/`: unit and integration-oriented harness tests
- `original/original_1998/`: unchanged source released with the 1998 paper
- `original/Updated/`: complete, ready-to-build C source used by the reference
  generator and C validation tests
- `reference/manifests/`: locked case, source, checkpoint, and paper metadata
- `reference/rendered/`: selected Updated C reference images

The large phase-dense trajectories, equilibration-checkpoint cache, and sparse
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

Long benchmark trials run as durable Kubernetes Jobs rather than as local
processes. The agent runs first in an isolated init container. If it succeeds,
the trusted evaluator runs in the same Job with read-only access to the
reference data. The default limits are 48 hours for the agent and 12 hours for
evaluation. Kubernetes keeps the pipeline running if the submitting terminal,
laptop, VPN, or provider client disconnects.

The current deployment target is RENCI's Sterling Kubernetes cluster. The
runner defaults, generated Job/PVC/NetworkPolicy resources, and committed
Kustomize proxy resources are tuned to Sterling's `bizon@sterling` context and
`bizon` namespace. This is not currently a generic Helm chart. Porting it to
another cluster requires reviewing the namespace, storage class, resource
quota, registry Secret, DNS/network-policy behavior, and provider egress
allowlist.

The Sterling setup requires:

- `kubectl` access to the `bizon` namespace with permission to create Jobs,
  Pods, PVCs, Secrets, and NetworkPolicies and to read pod logs
- dynamic `ReadWriteOnce` persistent storage for a 5-GiB reference PVC and a
  20-GiB PVC per active trial
- `linux/amd64` worker nodes and quota for the agent and evaluator resource
  requests
- a network-policy-capable CNI, cluster DNS in `kube-system`, and outbound
  HTTPS access through the benchmark's allowlisted proxy
- access to the benchmark images in GitHub Container Registry (GHCR); public
  images require no namespace pull Secret
- a local copy of the trusted dense-reference bundle for the initial upload

### Get the dense references

The dense-reference bundle is the evaluator's trusted expected output. It is
approximately 2.7 GiB uncompressed and contains validated phase-dense
trajectories and accepted restart checkpoints for cases `a`, `b`, `cd`, `e`,
`f`, `g`, and `h`, plus manifests and reference-generation gate reports. The
agent never sees or mounts it.

The release archive will contain a top-level `generated/` directory. Replace
the URL and checksum placeholders below after the archive is published:

```sh
export REFERENCE_ARCHIVE_URL=https://REPLACE-ME/granular-benchmark-reference-v1.zip
export REFERENCE_ARCHIVE_SHA256=eb4c942abedb100519a58e39867dd2ea0ee148090df82d5dc12fe753ba7c5d09

mkdir -p artifacts/reference
curl --fail --location "$REFERENCE_ARCHIVE_URL" \
  --output artifacts/granular-benchmark-reference-v1.zip
printf '%s  %s\n' \
  "$REFERENCE_ARCHIVE_SHA256" artifacts/granular-benchmark-reference-v1.zip \
  | shasum -a 256 --check
unzip -q artifacts/granular-benchmark-reference-v1.zip -d artifacts/reference

export REFERENCE_ROOT="$PWD/artifacts/reference/generated"
uv run balls-bench validate-reference \
  "$REFERENCE_ROOT/manifest.json" \
  --load-trajectories
```

Until that archive is published, the copy on the current development machine
is available in the sibling checkout at
`../balls_56_independent/reference/generated`. Detailed reference contents and
generation procedures are documented in
[`reference/README.md`](reference/README.md).

### Configure Sterling

Build and publish the two Kubernetes images once for each benchmark-runtime
revision, then record the images and reference location:

```sh
export GHCR_OWNER=cbizon
export GHCR_TOKEN=YOUR_CLASSIC_PAT_WITH_WRITE_PACKAGES
export IMAGE_TAG=$(git rev-parse --short HEAD)

uv run balls-sterling preflight \
  --context bizon@sterling \
  --namespace bizon
printf '%s' "$GHCR_TOKEN" \
  | docker login ghcr.io --username "$GHCR_OWNER" --password-stdin

uv run balls-sterling build \
  --agent-image "ghcr.io/$GHCR_OWNER/granular-benchmark-agent:$IMAGE_TAG" \
  --evaluator-image "ghcr.io/$GHCR_OWNER/granular-benchmark-evaluator:$IMAGE_TAG" \
  --push

uv run balls-sterling configure \
  --context bizon@sterling \
  --namespace bizon \
  --agent-image "ghcr.io/$GHCR_OWNER/granular-benchmark-agent:$IMAGE_TAG" \
  --evaluator-image "ghcr.io/$GHCR_OWNER/granular-benchmark-evaluator:$IMAGE_TAG" \
  --reference-root "$REFERENCE_ROOT"
```

The token is used only to publish images. After the first push, set both GHCR
packages to public so Sterling can pull them without a registry Secret.

`configure` writes the Git-ignored `.balls-sterling.json` file. It records the
cluster, images, local reference path, storage sizes, overlap metric setting,
and deadlines, but no API keys. Use `--force` when
intentionally replacing an existing configuration.

Before the first trial for a provider, export its API key:

```sh
export AZURE_OPENAI_API_KEY=...  # Codex
export ANTHROPIC_API_KEY=...     # Claude
```

The first `run` creates the provider Secret if needed. It also creates,
uploads, and validates the `balls-bench-reference` PVC from `REFERENCE_ROOT`
if that claim does not already exist. The laptop must remain connected during
this initial upload. Later trials reuse both cluster resources.

### Select a model and provider

`MODEL` is the exact model identifier passed to the selected agent CLI. It is
not an API endpoint or a display label. Specify the provider explicitly rather
than relying on name-based inference:

```sh
# Codex using the configured RENCI Azure OpenAI endpoint
uv run balls-sterling run \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high

# Claude Code using the Anthropic API
uv run balls-sterling run \
  --provider claude \
  --model claude-fable-5 \
  --effort high
```

For Codex, use the Azure deployment/model identifier accepted by the configured
RENCI endpoint. The locally configured Codex catalog currently includes
`gpt-5.6-terra`, `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, and
`gpt-5.2-codex`, but that local catalog is not mounted into the benchmark
container. The container starts Codex with `--ignore-user-config` and passes
the requested model string and Azure provider settings directly.

For Claude Code, use a Claude model's full identifier, such as
`claude-fable-5`. If `--provider` is omitted, only identifiers beginning with
`claude` are inferred as Claude; every other identifier is inferred as Codex.
In particular, `--model fable` would incorrectly select Codex.

`--effort` is required. The harness does not inherit or guess the agent CLI's
default, so a benchmark result always records the exact reasoning effort used.
`low`, `medium`, and `high` are supported by both provider paths; `high` is the
recommended comparison setting and is used in the examples. Claude also
supports `max`. Known Codex models support these additional levels:

- `gpt-5.4`, `gpt-5.5`, and `gpt-5.2-codex`: through `xhigh`
- `gpt-5.6-luna`: through `max`
- `gpt-5.6-sol` and `gpt-5.6-terra`: through `ultra`

The harness rejects known unsupported provider/model/effort combinations before
submitting Kubernetes work. For an unrecognized Codex-compatible deployment,
it validates the effort spelling but lets the configured backend determine
whether that model supports it.

Codex can in principle drive a non-OpenAI model through an OpenAI-compatible
Responses API, but the current benchmark's Codex provider is fixed to the
RENCI Azure endpoint. A model appearing in that endpoint's catalog does not by
itself establish that it supports Codex's Responses API, structured output,
tool calling, and long-running agent behavior. Smoke-test models such as Kimi
before starting a 48-hour trial. Claude Code is not a general Kimi or GLM
runner; this benchmark's Claude path is for Claude models. A non-OpenAI model
run through Codex measures that model inside the Codex agent scaffolding, not
the model vendor's native coding agent.

After this setup, a complete trial is one command:

```sh
uv run balls-sterling run \
  --provider PROVIDER \
  --model MODEL \
  --effort EFFORT
```

That command chains cluster setup checks, provider selection, agent execution,
trusted evaluation, SHA-256-verified artifact retrieval, result validation, and
cleanup. The Kubernetes pipeline continues if the terminal, laptop, VPN, or
provider client connection disappears.

### Detach, monitor, and recover

Without `--detach`, `run` waits for the Kubernetes pipeline, retrieves and
verifies the result, and cleans up the trial resources. With `--detach`, it
returns as soon as Kubernetes accepts the durable Job. Detaching does not stop
or background a local process; the computation is already running in
Kubernetes and no longer depends on the laptop.

Use an explicit unique test ID when launching detached work:

```sh
uv run balls-sterling run \
  --detach \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high \
  --test-id codex-gpt-5-6-sol-01
```

The returned JSON includes the test ID, Kubernetes Job, and trial PVC. Check
resource state and recent agent logs with:

```sh
uv run balls-sterling status \
  --test-id codex-gpt-5-6-sol-01 \
  --logs \
  --tail 200
```

The agent is an init container. Once it finishes, inspect the evaluator
container using the Job name returned by `run`:

```sh
kubectl --context bizon@sterling --namespace bizon \
  logs job/JOB_NAME --container evaluator --tail=200
```

To wait for completion, retrieve and verify the artifacts, and clean up, rerun
the original command without `--detach`, preserving the provider, model,
effort, and test ID:

```sh
uv run balls-sterling run \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high \
  --test-id codex-gpt-5-6-sol-01
```

If no test ID is supplied, Git-ignored active-run state permits one active run
per exact provider/model/effort combination, and repeating the same command
resumes that run rather than launching a replica.

### Concurrent runs

Runs with unique test IDs receive separate Jobs, trial PVCs, NetworkPolicies,
and local result directories, so different model versions can run
concurrently. They share only the provider Secrets, proxy, and trusted
reference PVC. Cluster CPU, memory, and PVC quotas still limit practical
concurrency.

The shared reference PVC uses `ReadWriteMany`, while every evaluator mounts it
read-only. This permits concurrent Jobs on different Sterling nodes. The
one-time uploader is the only writable mount and marks a successful upload
with the validated reference-manifest digest. Per-trial PVCs remain
`ReadWriteOnce` because each belongs to one pipeline Pod.

See
[`harness/kubernetes/sterling/README.md`](harness/kubernetes/sterling/README.md)
for image configuration, isolation, and recovery details.

## Local trial workflow

The lower-level local workflow remains available for development:

```sh
uv run balls-bench trial-create tests \
  --provider codex \
  --model MODEL \
  --effort high \
  --test-id TEST_ID

uv run balls-bench trial-run tests/TEST_ID

uv run balls-bench trial-evaluate \
  tests/TEST_ID \
  /external/figure1/manifest.json
```

Evaluation writes the machine-readable metrics to
`tests/TEST_ID/evaluation/results.json` and a self-contained review viewer to
`tests/TEST_ID/evaluation/comparison.html`. The viewer compares representative
height fields, pattern metrics, scalar and rotational dynamics, and overlap
counts for every Figure 1 case. It also embeds the provider-recorded agent
transcript, including attempts, messages and reasoning summaries, commands and
their output, file changes, task lists, stderr, and final response metadata.
The top-level Global stats view reports model, effort, elapsed time, attempts,
and token usage. Private reasoning that the provider does not emit cannot be
reconstructed.

Each submitted case includes `walltime_seconds`, the elapsed time for the
simulation run that produced that case's trajectory. The Figure 1 view reports
that value with the submitted simulation cycle. The harness independently
records total agent elapsed time and reports it in Global stats.

The agent workspace contains only the staged challenge. It does not contain the
two C source trees, benchmark harness, trusted references, prior submissions,
or any excluded Python implementation.

## Metrics

Evaluation compares reference and candidate trajectories, paper-level pattern
features, physical totals, time profiles, and the prevalence and severity of
non-physical particle overlaps. Definitions are in
[`harness/METRICS.md`](harness/METRICS.md).

## Reference data

The canonical dense references begin their exported trajectories after
equilibration cycles `a=680`, `b=2700`, `f=212`, and `cd/g/h=300`, plus the
uninterrupted panel `e` crash window. See
[`reference/README.md`](reference/README.md) for generation and validation.
