# Phase 4B.3 Progressive Multiple-Choice study

A session stores one shuffle when it is created. The cache pass can save ready snapshots in a batch, and cache misses run in stored position order. The next question is always the first unanswered, nonfailed position. A pending position blocks access to the cards behind it. A permanent failure is recorded and skipped when the sequence reaches it.

With five or more cards, the first five playable questions in the resolved prefix enable **Start Studying**. A failure in that prefix can be passed once it is recorded. A shorter deck settles all its positions before study begins. The start action is idempotent and does not launch another preparation job.

After study starts, the `active` status can coexist with `preparing=true`. The client keeps polling preparation progress and shows a waiting state when it reaches a pending question. Grading validates the question and option IDs under the existing write lock. Refresh loads the same stored sequence and options. Navigating away stops browser polling while server preparation continues. Cancelling ends the session and stops its job. After a restart, the saved snapshots remain ready and interrupted positions can be retried. A retry in a started session leaves earlier permanent failures in place so it cannot rewind the sequence.

A per-question countdown begins when that question opens. An already-started deck timer keeps running through waiting and feedback. At the deck deadline, late answers are rejected and any pending worker settles or is stopped before showing the final result. Ordinary completion requires preparation to settle and all ready questions to be answered or consumed by timing.

## Method

The same synthetic 10-, 50-, and 150-card decks, seed, and cache scenarios from [Phase 4B.2](CACHE_FIRST.md) were used. The before point is the Phase 4B.2 worker's preparation completion, when the first question could be opened. The after point is the latest snapshot commit among the first five persisted positions. Every benchmark slot prepared successfully. This measures server eligibility and excludes the browser poll interval and click latency. The complete before and after totals are separately retained.

The harness uses the existing production worker with disposable SQLite. Live runs use local Qwen3 and scripted hybrid connection failures, like the baseline. The mocked runs replay fixed delays and retries without using the model.

~~~powershell
& ./docs/quality/run-performance.ps1 -Mode mock -OutName performance-progressive-mock
& ./docs/quality/run-performance.ps1 -Mode live -OutName performance-progressive-live
~~~

## Results

All benchmark scenarios prepared every card. Times start at enqueue.

### Live Ollama 0.40.16 with `qwen3:1.7b`

| Cards | Cache | Before playable (s) | After playable (s) | After total preparation (s) |
| ---: | --- | ---: | ---: | ---: |
| 10 | cold (model resident) | 6.592 | 3.420 | 6.665 |
| 10 | warm | 0.037 | 0.017 | 0.027 |
| 10 | hybrid | 2.533 | 2.570 | 3.546 |
| 50 | cold | 31.133 | 6.458 | 39.548 |
| 50 | warm | 0.033 | 0.014 | 0.027 |
| 50 | hybrid | 12.540 | 1.964 | 12.717 |
| 150 | cold | 93.675 | 3.081 | 119.960 |
| 150 | warm | 0.042 | 0.029 | 0.038 |
| 150 | hybrid | 37.278 | 3.474 | 43.280 |

The initial 10-card cold sample included loading the model. It took 9.505 s to be playable and 12.709 s to finish. The table uses a separate 10-card repeat with the model resident, like the baseline. The 150-card cold total varied between runs, and progressive eligibility arrived after about three seconds in the after run.

Two simultaneous cold 10-card sessions remained at a measured peak of 1 inference request. Their playable times changed from 11.215 / 11.749 s to 5.404 / 5.909 s. That pair uses the same local model slot and has to wait when another session is generating.

### Mocked control

| Cards | Cache | Before playable (s) | After playable (s) | After total preparation (s) |
| ---: | --- | ---: | ---: | ---: |
| 10 | cold | 0.678 | 0.393 | 0.714 |
| 10 | warm | 0.033 | 0.019 | 0.031 |
| 10 | hybrid | 0.340 | 0.219 | 0.327 |
| 50 | cold | 3.208 | 0.358 | 3.392 |
| 50 | warm | 0.033 | 0.025 | 0.039 |
| 50 | hybrid | 1.502 | 0.271 | 1.659 |
| 150 | cold | 9.592 | 0.400 | 9.607 |
| 150 | warm | 0.045 | 0.018 | 0.024 |
| 150 | hybrid | 4.198 | 0.366 | 4.204 |

The mocked and live hybrid runs preserve cache-first preparation. The fifth ready snapshot **anywhere** can be ready much sooner than the fifth playable position. On the live 150-card hybrid run, the anywhere milestone was 0.021 s and the ordered start milestone was 3.474 s.

## Verification

The regression suites passed 284 backend and 61 frontend tests. Browser verification with a delayed model fixture started a 12-card deck at five ready questions, answered all five, waited at position six, and reopened the session from deck history. The next question appeared with all five answers saved. The SQLite migration rehearsal preserved existing rows and foreign keys.

## Remaining limits

Slow inference inside the first five positions can delay the start. Later pauses can occur at the first unresolved position, even when other snapshots are cached. The live workload uses short synthetic questions and one local model. The browser usually picks up a readiness change on the next poll, which adds up to roughly 1.5 seconds while the tab is active, plus network time. The single Ollama slot remains a throughput limit for concurrent cold sessions. Background preparation is tied to the backend process. A stopped worker is recovered as interrupted and can be retried.

## Evidence

- [Before benchmark](CACHE_FIRST.md#live-comparison)
- [After live raw measurements](results/performance-progressive-live.json) and [live host samples](results/performance-progressive-live-host.csv)
- [Resident 10-card cold repeat](results/performance-progressive-live-10-resident.json)
- [After mocked raw measurements](results/performance-progressive-mock.json) and [mocked host samples](results/performance-progressive-mock-host.csv)
