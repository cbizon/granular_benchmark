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

The cluster needs published `linux/amd64` images. Choose registry names and
build them when the benchmark runtime changes:

```sh
uv run balls-sterling build \
  --agent-image docker.io/USER/balls-bench-agent:TAG \
  --evaluator-image docker.io/USER/balls-bench-evaluator:TAG \
  --push
```

Record those image names and the registry pull Secret once:

```sh
uv run balls-sterling configure \
  --agent-image docker.io/USER/balls-bench-agent:TAG \
  --evaluator-image docker.io/USER/balls-bench-evaluator:TAG \
  --image-pull-secret image-pull-secret
```

The configuration is stored in the ignored `.balls-sterling.json` file. It
contains image and cluster settings, but no API key values. Before the first
trial for each provider, export its key locally:

```sh
export AZURE_OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

`run` copies a missing key into the provider-specific Kubernetes Secret. Once
the Secret exists, the local environment variable is no longer required.

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
