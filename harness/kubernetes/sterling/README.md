# Sterling runner

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

## One-time configuration

Run the following setup from the repository root. It requires:

- RENCI VPN access and a working `bizon@sterling` Kubernetes context
- Docker with `buildx`, logged into Docker Hub
- the Sterling `image-pull-secret`, which lets the cluster pull those images
- a local copy of the large phase-dense reference dataset, including
  `manifest.json`

Set the image owner, an immutable image tag, and the reference location:

```sh
export DOCKERHUB_USER=YOUR_DOCKERHUB_ACCOUNT
export IMAGE_TAG=$(git rev-parse --short HEAD)
export REFERENCE_ROOT=/absolute/path/to/balls_56_independent/reference/generated

test -f "$REFERENCE_ROOT/manifest.json"
kubectl --context bizon@sterling --namespace bizon get pods
kubectl --context bizon@sterling --namespace bizon get secret image-pull-secret
docker login docker.io
```

For the development checkouts used to create this benchmark, the reference
root is `../balls_56_independent/reference/generated`. The dense references
are external because they are too large for this Git repository.

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
