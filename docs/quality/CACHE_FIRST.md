# Phase 4B.2 Cache-first scheduling

The preparation worker checks pending questions for valid cached distractors in one SQLite transaction. It saves those question snapshots at their assigned shuffled positions before queuing misses. The cache pass verifies the question content, configured model, generation version, and recorded deck-answer dependencies. It copies photo blobs within SQLite when creating the snapshots.

Misses retain the normal cache recheck and per-card generation lock. A different session can fill a miss between the cache pass and the recheck. The shared model slot is acquired only around Ollama inference. SQLite reads, fallback selection, and snapshot writes run outside that slot. The worker owns no database transaction during inference.

A cached snapshot keeps its existing question position, original correct answer, and generated option IDs. Ready snapshots are recorded internally. The session still opens for study when preparation settles as active or the student continues with the ready subset from a failed preparation.

## Reproduction and comparison

The before results are from [Phase 4B.1](PERFORMANCE.md), including its isolated 150-card cold repeat. The same workload generator, hardware, local model, seed, artificial hybrid outages, and mocked response schedule were used for the after runs. The timing harness supports both workers. It records the commit time of the cache pass as the time every snapshot in that batch becomes ready. Batched cards therefore share one readiness time. First-, fifth-, and last-ready comparisons use committed snapshots in both versions.

Run from the repository root in PowerShell 7.

~~~powershell
& ./docs/quality/run-performance.ps1 -Mode mock -OutName performance-cache-first-mock
& ./docs/quality/run-performance.ps1 -Mode live -OutName performance-cache-first-live
~~~

The benchmark uses synthetic, photo-free decks of 10, 50, and 150 cards and disposable SQLite. Run the Windows host-sample merger from [the baseline methodology](PERFORMANCE.md#reproduce) using the corresponding run names. Raw results retain individual attempts, measured cache hits, and query counts. Exact live timings vary with model residency, runtime load, and sampling noise.

## Live comparison

Times are in seconds. Each cell shows before → after. Readiness starts at enqueue. Total wall time also includes session creation.

| Deck size | Cache | First ready | Fifth ready | Total wall |
| ---: | --- | ---: | ---: | ---: |
| 10 | cold | 7.039 → 0.943 | 9.421 → 3.473 | 12.692 → 6.608 |
| 10 | warm | 0.019 → 0.020 | 0.089 → 0.020 | 0.228 → 0.053 |
| 10 | hybrid | 0.589 → 0.010 | 2.015 → 0.010 | 2.723 → 2.552 |
| 50 | cold | 0.640 → 0.582 | 3.180 → 3.088 | 32.328 → 31.153 |
| 50 | warm | 0.020 → 0.021 | 0.103 → 0.021 | 0.893 → 0.047 |
| 50 | hybrid | 0.617 → 0.022 | 2.110 → 0.022 | 13.785 → 12.558 |
| 150 | cold | 0.935 → 0.578 | 3.390 → 3.080 | 94.456 → 93.710 |
| 150 | warm | 0.009 → 0.035 | 0.066 → 0.035 | 1.783 → 0.085 |
| 150 | hybrid | 0.710 → 0.015 | 2.507 → 0.015 | 39.437 → 37.291 |

- **150-card hybrid:** 75 cached snapshots committed together in the first 0.015 s. Both versions sent 60 live requests and rescued 15 simulated outages using deck answers. SQL statement count fell from 1692 to 948, and wall time fell from 39.437 s to 37.291 s.
- **150-card warm:** SQL statement count fell from 1512 to 18. The batch commit increased time to the first ready snapshot at that size but delivered the first five sooner and shortened the full run. Neither run needed Ollama.
- **150-card cold:** The optimized run still sent 150 live requests. Generator wall time was 88.619 s of 93.710 s overall. The small total-time difference warrants no speedup claim for cold inference. The original 10-card cold run incurred model load time, so the 10-card totals include different model residency.

All live and mocked scenarios had every card ready and zero failed cards. The concurrent live benchmark kept a peak of one in-flight model request in both versions.

### Contention

For two simultaneous cold 10-card sessions, total wall time was 12.110 → 11.763 s. Median wait for the shared model slot was 562 → 519 ms for those cold workloads. The after value measures waiting to enter inference. The baseline waited before source and cache lookups too. A separate deterministic regression holds Ollama in one session and verifies that a warm Multiple-Choice session and a Classic review finish before releasing the model slot.

| Concurrent session | First ready before → after (s) | Fifth ready before → after (s) | Preparation before → after (s) |
| ---: | ---: | ---: | ---: |
| 1 | 0.624 → 0.591 | 5.507 → 5.320 | 11.492 → 11.215 |
| 2 | 1.201 → 1.150 | 6.053 → 5.864 | 12.091 → 11.749 |

### Mocked control

These runs used 30 ms fixture responses and scripted retries. They measure orchestration under controlled delays.

| Deck size | Cache | Wall before → after (s) | After fixture requests / retries |
| ---: | --- | ---: | ---: |
| 150 | cold | 9.163 → 9.608 | 165 / 15 |
| 150 | warm | 1.419 → 0.072 | 0 / 0 |
| 150 | hybrid | 5.000 → 4.216 | 90 / 15 |
| 2 × 10 | two_cold_sessions | 1.105 → 0.765 | 22 / 2 |

## Regression tests

All 277 backend tests passed across the generator, cache, Multiple-Choice sessions, Classic study and scheduling. New cases verify mixed preparation order and stable option IDs, photo snapshots, stale cache entries, and warm Multiple-Choice and Classic progress while a cold session holds the model slot.

## Remaining bottlenecks

Ollama still dominates cold and partially cached sessions. Cold sessions still share one inference slot. The cache pass retains a SQLite write transaction through validation and snapshot commit to prevent races with card edits and source invalidation. Photo-heavy snapshots are copied inside SQLite. The duration of that transaction for large decks with photos needs separate measurement.

## Artifacts

- [After live per-card traces](results/performance-cache-first-live.json), [live summary](results/performance-cache-first-live-summary.json), [Windows host samples](results/performance-cache-first-live-host.csv), [hardware](results/performance-cache-first-live-hardware.json) and [loaded Ollama model](results/performance-cache-first-live-ollama.json)
- [After mocked per-card traces](results/performance-cache-first-mock.json), [mocked summary](results/performance-cache-first-mock-summary.json) and [mocked host samples](results/performance-cache-first-mock-host.csv)
- [Before measurements and raw files](PERFORMANCE.md#captured-results)
