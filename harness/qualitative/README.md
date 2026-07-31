# Qualitative evaluation

This directory defines the canonical qualitative-review contract for the
benchmark. It is evaluator material and is not part of the challenge presented
to the executing agent.

## Files

- `RUBRIC.md`: Human-readable criteria and rating anchors.
- `reviewer-prompt.md`: Fixed instructions for the reviewer agent.
- `qualitative-review.schema.json`: Machine-readable reviewer output contract.

The repository files are authoritative. A Codex skill may later provide a thin
interactive wrapper, but it must not carry an independent copy of the rubric.

## Intended workflow

1. The deterministic evaluator writes `evaluation/results.json`, comparison
   images, global statistics, and normalized transcript data.
2. The harness assembles a lightweight `evaluation/review-input.json` dossier
   containing paths, deterministic metrics, test results, timeline facts, and
   artifact hashes.
3. A fixed reviewer model receives the dossier, candidate code, this rubric,
   and `reviewer-prompt.md`. Candidate provider and model identity should be
   hidden where practical.
4. The reviewer writes `evaluation/qualitative-review.json`.
5. The harness validates that file against
   `qualitative-review.schema.json`.
6. The harness calls `refresh_comparison_viewer()` to embed the review in the
   existing self-contained report.
7. The comparison viewer renders a top-level `Qualitative Review` page, and
   the campaign viewer renders a cross-trial matrix.

The qualitative review should run after deterministic evaluation and before
trial cleanup. Only the lightweight JSON, code, transcript, metrics, and
rendered artifacts need to be retained locally; trajectories remain optional.

## Comparison behavior

The viewer may map ratings as follows:

| Rating | Display value |
| --- | ---: |
| `correct` | 3 |
| `mostly_correct` | 2 |
| `mostly_incorrect` | 1 |
| `incorrect` | 0 |
| `uncertain` | no numeric value |
| `not_applicable` | no numeric value |

These values support heatmaps and filtering. They must not be summed into a
single ranking across different simulation classes.

The campaign view should lead with:

1. simulation class;
2. algorithm tier;
3. event-driven fidelity, when applicable;
4. Figure 1 fidelity;
5. physical fidelity;
6. numerical treatment;
7. tests and reproducibility;
8. transcript and time-use summary.

## Time-accounting limitation

Provider transcripts do not expose exact private thinking time and do not
always timestamp every event. The harness should calculate defensible timing
facts before review:

- attempt start and end times;
- provider-reported inference or API duration;
- foreground tool intervals;
- background-task intervals;
- runner retry and subscription-wait intervals;
- unclassified elapsed time.

The reviewer summarizes those facts and describes uncertainty. It must not
invent a complete wall-clock partition when intervals overlap or timestamps
are absent.
