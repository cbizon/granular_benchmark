# Sterling Kubernetes runner

The benchmark uses Kubernetes to make 48-hour agent trials independent of the
submitting laptop. One durable Job contains:

1. an isolated agent init container with the challenge, provider credentials,
   an allowlisted HTTPS proxy, and a writable trial PVC
2. a trusted evaluator container that starts after the agent runner records a
   terminal outcome and mounts the trial PVC plus the reference PVC read-only

The evaluator receives no provider credentials or proxy environment and does
not require outbound network access. The agent cannot mount the trusted
references. NetworkPolicy is applied at the shared Pod level, so this
separation also depends on the trusted evaluator image and container
configuration.

This implementation currently targets RENCI's Sterling cluster. The Python
runner defaults to Kubernetes context `bizon@sterling` and namespace `bizon`.
The committed Kustomize resources under `proxy/` also target `bizon`, and the
runner rejects a different namespace for that proxy installation. The
generated resources assume Sterling's storage, DNS, network-policy, registry,
and scheduling behavior. They are Kubernetes manifests, not a portable Helm
chart.

After one-time configuration, a benchmark trial is one command:

```sh
uv run balls-sterling run \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high
```

For Claude, use the full Claude model identifier:

```sh
uv run balls-sterling run \
  --provider claude \
  --model claude-fable-5 \
  --effort high

uv run balls-sterling run \
  --provider claude \
  --model claude-haiku-4-5
```

`MODEL` is passed unchanged to the selected agent CLI. It is not the endpoint
URL or a display label. The container invokes Codex with
`--ignore-user-config`, so it does not read the submitting machine's Codex
catalog. If `--provider` is omitted, model names beginning with `claude` select
Claude and all other names select Codex; explicit provider selection is
recommended. `fable` alone would therefore select Codex, while
`claude-fable-5` selects Claude.

`--effort` is optional. When supplied, it becomes part of the durable trial
identity and metadata and is passed to the selected agent CLI. When omitted,
the metadata records `null`, no effort argument is sent, and the model or
provider chooses its default behavior. Omit it for models without effort
control, such as Claude Haiku 4.5. Known Codex model limits are:

- `gpt-5.4`, `gpt-5.5`, and `gpt-5.2-codex`: `low` through `xhigh`
- `gpt-5.6-luna`: `low` through `max`
- `gpt-5.6-sol` and `gpt-5.6-terra`: `low` through `ultra`

Known invalid Codex combinations fail before Kubernetes submission. Other
models are passed through after validating the effort name; the caller and
configured backend determine whether that model supports the selected level.

Codex can use a non-OpenAI model only when the configured provider implements
the Responses API and the model supports the tool and structured-output
behavior Codex requires. The current Codex path is configured for RENCI Azure.
Claude Code is used here only with Claude models.

The command verifies Sterling access, installs or updates the allowlisted
proxy, creates the provider Secret from the corresponding local environment
variable when it is absent, ensures the trusted reference PVC exists, and
submits one durable Kubernetes Job. Codex uses `AZURE_OPENAI_API_KEY`. Claude
uses subscription OAuth from `CLAUDE_CODE_OAUTH_TOKEN`; the Claude container
does not accept `ANTHROPIC_API_KEY` or use `--bare`. That Job runs the agent and
then the evaluator without depending on the laptop. The command waits for the
Job, retrieves every trial artifact, verifies the copy by SHA-256, validates
the required benchmark outputs, and deletes the workload and trial PVC.

Results are written under `tests/TEST_ID/result`.

## Kubernetes prerequisites

An operator or cluster administrator must provide:

- a namespace and credentials with permission to create Jobs, Pods,
  `ReadWriteOnce` and `ReadWriteMany` PVCs, Secrets, Services, Deployments,
  ConfigMaps, and NetworkPolicies, to patch PVC annotations, and to read pod
  logs
- dynamic persistent-volume provisioning; Sterling currently uses the
  namespace's default storage class
- `linux/amd64` worker nodes
- enough quota for a trial pod requesting 3 CPUs and 16 GiB of memory, with
  limits of 8 CPUs and 64 GiB, a temporary reference validator requesting
  1 CPU and 2 GiB with limits of 4 CPUs and 8 GiB, plus a small Squid proxy
- a CNI that enforces Kubernetes NetworkPolicies
- DNS reachable in a namespace labeled
  `kubernetes.io/metadata.name=kube-system`
- outbound TCP 443 from the proxy to the configured provider endpoints
- access to the configured container registry; public GHCR images require no
  image-pull Secret

The default persistent resources are:

- `balls-bench-reference`: 5-GiB reference PVC, retained across trials
- one 20-GiB trial PVC per active model run, deleted after verified collection

The `balls-sterling preflight` command checks the context and the namespace
permissions used by the runner. It cannot provision cluster storage, install a
network-policy CNI, create registry credentials, or grant RBAC.

## Dense-reference bundle

The dense references are the benchmark's trusted evaluator inputs, not source
material given to the model. The approximately 2.7-GiB uncompressed collection
contains:

- a top-level `manifest.json`
- directories `a`, `b`, `cd`, `e`, `f`, `g`, and `h`
- a validated `trajectory.npz`, accepted `checkpoint.restart`, and case
  `manifest.json` in each case directory
- `_gates/` reports tying generation to the qualified `Updated` C source

The release ZIP will unpack to `generated/`. Replace the placeholders when the
archive URL and checksum are published:

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

Until the release archive exists, maintainers can use the sibling development
checkout:

```sh
export REFERENCE_ROOT="$PWD/../balls_56_independent/reference/generated"
```

The first `balls-sterling run` streams this directory through `kubectl exec`
into `balls-bench-reference` and validates it inside the evaluator image. The
local machine and VPN must remain available for that initial upload. The
completed reference PVC is reused by subsequent trials and is never mounted by
the agent.

## One-time Sterling configuration

Run the following setup from the repository root. It requires:

- RENCI VPN access and a working `bizon@sterling` Kubernetes context
- Docker with `buildx`
- a GitHub personal access token (classic) with `write:packages` permission
  for publishing to GHCR
- the validated `REFERENCE_ROOT` prepared above

Check access and set the image owner and an immutable image tag:

```sh
export GHCR_OWNER=cbizon
export GHCR_TOKEN=YOUR_CLASSIC_PAT_WITH_WRITE_PACKAGES
export IMAGE_TAG=$(git rev-parse --short HEAD)

kubectl --context bizon@sterling --namespace bizon get pods
uv run balls-sterling preflight \
  --context bizon@sterling \
  --namespace bizon
printf '%s' "$GHCR_TOKEN" \
  | docker login ghcr.io --username "$GHCR_OWNER" --password-stdin
```

Build both `linux/amd64` images and push them to GHCR:

```sh
uv run balls-sterling build \
  --agent-image "ghcr.io/$GHCR_OWNER/granular-benchmark-agent:$IMAGE_TAG" \
  --evaluator-image "ghcr.io/$GHCR_OWNER/granular-benchmark-evaluator:$IMAGE_TAG" \
  --push
```

Set both packages to public in their GitHub package settings after the first
push. Public packages let Sterling pull anonymously and avoid another
long-lived registry credential in the cluster. If private packages are
required instead, create a `kubernetes.io/dockerconfigjson` Secret for
`ghcr.io` in `bizon` and pass its name with `--image-pull-secret`.

Record the image names and local reference location:

```sh
uv run balls-sterling configure \
  --context bizon@sterling \
  --namespace bizon \
  --agent-image "ghcr.io/$GHCR_OWNER/granular-benchmark-agent:$IMAGE_TAG" \
  --evaluator-image "ghcr.io/$GHCR_OWNER/granular-benchmark-evaluator:$IMAGE_TAG" \
  --reference-root "$REFERENCE_ROOT"
```

This writes the Git-ignored `.balls-sterling.json` file. It contains the image
names, cluster settings, local reference path, storage sizes, repetition
count, overlap-metric setting, 48-hour agent deadline, and 12-hour evaluation
deadline. It contains no API key values. `configure` refuses to replace a
different existing configuration unless `--force` is supplied.

Rebuild and reconfigure when the agent or evaluator runtime changes. A new
model trial does not require new images.

Before the first Codex trial, export its key locally:

```sh
export AZURE_OPENAI_API_KEY=...
```

Before the first Claude trial, authenticate Claude Code locally with the
subscription account and generate a long-lived token:

```sh
claude setup-token
export CLAUDE_CODE_OAUTH_TOKEN='TOKEN_PRINTED_BY_CLAUDE'
```

`run` copies a missing credential into the provider-specific Kubernetes
Secret. Once the Secret exists, the local environment variable is no longer
required. Claude receives an empty writable `HOME` and `CLAUDE_CONFIG_DIR`
under `/tmp`; no host Claude configuration is mounted. On the first run, the
command also creates `balls-bench-reference` and uploads `REFERENCE_ROOT` if
that PVC is absent. Later trials reuse the reference PVC. The laptop must
remain connected while this one-time upload is happening; the durable trial
Job no longer depends on it after submission.

## Disconnection and recovery

The default command remains attached so it can collect results immediately,
but the Kubernetes pipeline continues if the terminal, laptop, VPN, or Azure
client connection disappears. Use `--detach` to return immediately after
Kubernetes accepts the Job:

```sh
uv run balls-sterling run \
  --detach \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high \
  --test-id codex-gpt-5-6-sol-01
```

An attached run prints phase changes and immediately reports recent logs from
an agent or evaluator container that exits unsuccessfully. It does not emit a
line for every Kubernetes status poll.

The returned JSON identifies the Job, PVC, and test ID. Monitor resources and
the agent init-container log with:

```sh
uv run balls-sterling status \
  --test-id codex-gpt-5-6-sol-01 \
  --logs \
  --tail 200
```

When the evaluator is running, inspect its log using the Job name returned by
`run`:

```sh
kubectl --context bizon@sterling --namespace bizon \
  logs job/JOB_NAME --container evaluator --tail=200
```

Run the original command again without `--detach`, preserving any explicit
effort and test ID, to wait, collect, verify, and clean up:

```sh
uv run balls-sterling run \
  --provider codex \
  --model gpt-5.6-sol \
  --effort high \
  --test-id codex-gpt-5-6-sol-01
```

Without an explicit test ID, Git-ignored active-run state permits one active
run per exact provider/model/effort setting. Omitted effort is a distinct
setting. Repeated invocations map to the same Job. `--retain-pvc` keeps the
trial PVC after a verified local copy.

## Concurrent trials

Unique test IDs produce separate Jobs, trial PVCs, NetworkPolicies, manifests,
and result directories. Provider Secrets and the proxy are intentionally
shared. The trusted reference PVC uses `ReadWriteMany`; only the one-time
uploader mounts it writable, and every evaluator mounts it read-only.
Per-trial PVCs remain `ReadWriteOnce`.

## Campaign orchestration

A campaign plan is a JSON object with a name, desired concurrency, and run
specifications:

```json
{
  "schema_version": 1,
  "name": "figure-1-model-sweep",
  "concurrency": 2,
  "runs": [
    {
      "provider": "codex",
      "model": "gpt-5.6-sol",
      "effort": "high",
      "run_count": 3
    },
    {
      "provider": "claude",
      "model": "claude-haiku-4-5",
      "effort": null,
      "run_count": 2
    }
  ]
}
```

Run or resume it with:

```sh
uv run balls-sterling orchestrate campaigns/example.json
```

The orchestrator:

- keeps up to the requested concurrency active, constrained by live namespace
  quota
- retrieves and validates completed results
- retrieves and checksum-verifies failed-trial artifacts before deleting a PVC
- retains a failed-trial PVC when artifact recovery itself fails
- records failed-container logs locally
- serves current status and collected report links at
  `http://127.0.0.1:8767/`
- persists state atomically under `.balls-sterling-campaigns/`

If Kubernetes becomes unreachable, the process records why it stopped and
exits without changing remote Jobs. Repeating the same command after
connectivity returns reconciles the saved state before launching more work.
The campaign plan contains desired work, not runtime `status`; status is in the
generated state file. Do not edit a plan after state has been created for it.

## Isolation

The agent runs as an init container with the staged challenge, provider Secret,
trial PVC, and allowlisted provider proxy. It does not mount the reference
volume. Non-retryable provider errors stop immediately. The final 30 minutes of
the agent budget are reserved for a provider-session finalization attempt that
preserves existing work and writes the best available status. The evaluator
starts after the runner records any terminal outcome, including `timeout` or
`provider_error`; it mounts the reference read-only but receives no provider
Secret or proxy environment. Evaluation includes the overlap metrics by
default.

The older `launch`, `status`, `collect`, and `cleanup` commands remain available
for diagnosis and manual recovery, but they are not part of the normal
benchmark workflow.
