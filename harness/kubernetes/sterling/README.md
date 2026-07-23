# Sterling Kubernetes runner

The benchmark uses Kubernetes to make 48-hour agent trials independent of the
submitting laptop. One durable Job contains:

1. an isolated agent init container with the challenge, provider credentials,
   an allowlisted HTTPS proxy, and a writable trial PVC
2. a trusted evaluator container that starts only after the agent succeeds and
   mounts the trial PVC plus the reference PVC read-only

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
uv run balls-sterling run --model gpt-5.6-sol
```

For Claude, use the Claude model name:

```sh
uv run balls-sterling run --model claude-sonnet-4-5
```

The command infers the provider, verifies Sterling access, installs or updates
the allowlisted proxy, creates the provider Secret from the corresponding local
environment variable when it is absent, ensures the trusted reference PVC
exists, and submits one durable Kubernetes Job. That Job runs the agent and
then the evaluator without depending on the laptop. The command waits for the
Job, retrieves every trial artifact, verifies the copy by SHA-256, validates
the required benchmark outputs, and deletes the workload and trial PVC.

Results are written under `tests/TEST_ID/result`.

## Kubernetes prerequisites

An operator or cluster administrator must provide:

- a namespace and credentials with permission to create Jobs, Pods,
  `ReadWriteOnce` PVCs, Secrets, Services, Deployments, ConfigMaps, and
  NetworkPolicies and to read pod logs
- dynamic persistent-volume provisioning; Sterling currently uses the
  namespace's default storage class
- `linux/amd64` worker nodes
- enough quota for a trial pod requesting 4 CPUs and 16 GiB of memory, with
  limits of 16 CPUs and 64 GiB, plus a small Squid proxy
- a CNI that enforces Kubernetes NetworkPolicies
- DNS reachable in a namespace labeled
  `kubernetes.io/metadata.name=kube-system`
- outbound TCP 443 from the proxy to the configured provider endpoints
- a container registry and an image-pull Secret in the trial namespace

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
export REFERENCE_ARCHIVE_SHA256=REPLACE_WITH_PUBLISHED_SHA256

mkdir -p artifacts/reference
curl --fail --location "$REFERENCE_ARCHIVE_URL" \
  --output artifacts/granular-benchmark-reference.zip
printf '%s  %s\n' \
  "$REFERENCE_ARCHIVE_SHA256" artifacts/granular-benchmark-reference.zip \
  | shasum -a 256 --check
unzip -q artifacts/granular-benchmark-reference.zip -d artifacts/reference

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
- Docker with `buildx`, logged into Docker Hub
- the Sterling `image-pull-secret`, which lets the cluster pull those images
- the validated `REFERENCE_ROOT` prepared above

Check access and set the image owner and an immutable image tag:

```sh
export DOCKERHUB_USER=YOUR_DOCKERHUB_ACCOUNT
export IMAGE_TAG=$(git rev-parse --short HEAD)

kubectl --context bizon@sterling --namespace bizon get pods
kubectl --context bizon@sterling --namespace bizon get secret image-pull-secret
uv run balls-sterling preflight \
  --context bizon@sterling \
  --namespace bizon
docker login docker.io
```

Build both `linux/amd64` images and push them to Docker Hub:

```sh
uv run balls-sterling build \
  --agent-image "docker.io/$DOCKERHUB_USER/balls-bench-agent:$IMAGE_TAG" \
  --evaluator-image "docker.io/$DOCKERHUB_USER/balls-bench-evaluator:$IMAGE_TAG" \
  --push
```

Record the image names and local reference location:

```sh
uv run balls-sterling configure \
  --context bizon@sterling \
  --namespace bizon \
  --agent-image "docker.io/$DOCKERHUB_USER/balls-bench-agent:$IMAGE_TAG" \
  --evaluator-image "docker.io/$DOCKERHUB_USER/balls-bench-evaluator:$IMAGE_TAG" \
  --image-pull-secret image-pull-secret \
  --reference-root "$REFERENCE_ROOT"
```

This writes the ignored `.balls-sterling.json` file. It contains the image
names, cluster settings, local reference path, storage sizes, repetition
count, overlap-metric setting, 48-hour agent deadline, and 12-hour evaluation
deadline. It contains no API key values. `configure` refuses to replace a
different existing configuration unless `--force` is supplied.

Rebuild and reconfigure when the agent or evaluator runtime changes. A new
model trial does not require new images.

Before the first trial for each provider, export its key locally:

```sh
export AZURE_OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

`run` copies a missing key into the provider-specific Kubernetes Secret. Once
the Secret exists, the local environment variable is no longer required. On
the first run, it also creates `balls-bench-reference` and uploads
`REFERENCE_ROOT` if that PVC is absent. Later trials reuse the reference PVC.
The laptop must remain connected while this one-time upload is happening; the
durable trial Job no longer depends on it after submission.

## Disconnection and recovery

The default command remains attached so it can collect results immediately,
but the Kubernetes pipeline continues if the terminal, laptop, VPN, or Azure
client connection disappears. Run the same command again:

```sh
uv run balls-sterling run --model gpt-5.6-sol
```

An ignored active-run record maps that model back to the existing Kubernetes
Job. The command resumes monitoring or, if computation already finished,
retrieves and verifies the artifacts. It records artifact verification before
cleanup, so an interruption during cleanup cannot relaunch the completed
trial.

Use `--detach` to return as soon as Kubernetes accepts the durable pipeline.
Use the same model-only command later to finish collection. `--retain-pvc`
keeps the trial PVC after a verified local copy.

## Isolation

The agent runs as an init container with the staged challenge, provider Secret,
trial PVC, and allowlisted provider proxy. It does not mount the reference
volume. The evaluator starts only after the agent succeeds; it mounts the
reference read-only but receives no provider Secret or proxy environment.
Evaluation includes the overlap metrics by default.

The older `launch`, `status`, `collect`, and `cleanup` commands remain available
for diagnosis and manual recovery, but they are not part of the normal
benchmark workflow.
