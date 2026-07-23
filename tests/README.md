# Benchmark trial records

`balls-bench trial-create` creates:

```text
<test-id>/{metadata,workspace,transcript,usage,timing,evaluation}/
```

The workspace and generated run records are ignored by Git by default because
they can be large or contain provider metadata. The committed harness defines
their schemas and parsers.

For Sterling, the normal entry point is:

```sh
uv run balls-sterling run --model MODEL
```

It creates the test identity, runs the agent and evaluator in one durable
Kubernetes pipeline, verifies the retrieved artifact checksums, and writes the
result below the generated test directory.
