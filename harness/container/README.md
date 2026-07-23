# Isolated agent runtime

Build the image while network access is available:

```sh
docker compose -f harness/container/compose.yaml build agent
```

Set `TRIAL_WORKSPACE` to the absolute staged workspace and provide only the API
key for the selected provider. Start the proxy, then run the provider command in
the `agent` service. The agent service is attached only to an internal network;
Squid is the sole egress path and permits provider API domains only.
The provider adapters separately disable Claude `WebSearch`/`WebFetch` and
Chrome integration, and disable Codex web-search, browser, computer-use, app,
and remote-plugin features.

The workspace mount must contain only the staged challenge. Do not mount this
repository, reference artifacts, C source trees, or prior submissions into
the agent service.

Sterling uses the same agent image with a PVC-backed resumable runner. Its
trusted evaluation runs from `Dockerfile.evaluator`, which is deliberately a
separate image so evaluator code and Updated C references are never exposed
to the agent. See `harness/kubernetes/sterling/README.md`.
