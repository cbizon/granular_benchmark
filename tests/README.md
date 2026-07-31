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
uv run balls-sterling run \
  --provider PROVIDER \
  --model MODEL \
  --effort high
```

It creates the test identity, runs the agent and evaluator in one durable
Kubernetes pipeline, verifies the retrieved artifact checksums, and writes the
result below the generated test directory. Each completed evaluation includes
`evaluation/results.json` and the self-contained
`evaluation/comparison.html` review viewer. The viewer includes both the
deterministic comparison plots, global model/time/token statistics, and the
provider-recorded agent activity transcript for each attempt. If
`evaluation/qualitative-review.json` has been generated, the viewer also
includes the structured qualitative rubric review as its default top-level
page.

Trajectory NPZ files are not retrieved by default because the evaluator has
already converted them into the report and machine-readable metrics. Add
`--keep-trajectories` to `balls-sterling run`, `collect`, or `orchestrate` when
the raw particle histories are required locally.
