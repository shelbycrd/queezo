# Multiple-Choice distractor QA

Phase 4A evaluates cold generation against 108 synthetic cards in 13 decks. The dataset has 12 cards in each of nine categories. Repeated Back text, some alternative number representations, and the original four-card keyboard-mash reproduction are intentional. The evaluator uses temporary SQLite databases and synthetic accounts. It never connects to the application's database.

- [Dataset](flashcards.json)
- [Captured live results](results/live.json)
- [Captured mocked results](results/mock.json)
- [Findings](FINDINGS.md)
- [Human-review rubric](REVIEW_RUBRIC.md)
- [Preliminary rubric review](sample-review.csv)
- [Phase 4B.1 performance benchmark](PERFORMANCE.md)
- [Phase 4B.2 cache-first benchmark](CACHE_FIRST.md)
- [Phase 4B.3 progressive study benchmark](PROGRESSIVE_STUDY.md)

## Reproduce the benchmark

From the repository root in PowerShell, build a dedicated image.

~~~powershell
docker compose -p queezo-quality build backend
$quality = Join-Path (Get-Location) 'docs/quality'
~~~

Run the deterministic transport fixtures without network access. Write a separate report to keep the captured run available for comparison.

~~~powershell
docker run --rm --network none --mount "type=bind,source=$quality,target=/quality" -e PYTHONPATH=/app queezo-quality-backend python /quality/evaluate.py --mode mock --seed 42 --out /quality/results/mock-rerun.json
~~~

For live sampling, start the existing local Ollama runtime with `qwen3:1.7b` installed.

~~~powershell
docker run --rm --mount "type=bind,source=$quality,target=/quality" -e PYTHONPATH=/app -e OLLAMA_BASE_URL=http://host.docker.internal:11434 -e OLLAMA_MODEL=qwen3:1.7b queezo-quality-backend python /quality/evaluate.py --mode live --seed 42 --out /quality/results/live-rerun.json
~~~

The code uses the seed for Python choice sampling and a per-card Ollama seed for the live requests. The reports record the dataset SHA-256, generator version, and model name. The live report also records the Ollama version and model digest. Hardware and Ollama runtime differences can still change live outputs. The scripted fixture rates characterize the known fixture sequence.

## Evaluation arms and denominators

| Arm | Meaning |
| --- | --- |
| AI-only | Use the production generator. Success means three structurally valid candidates after at most three requests. Partial candidates are kept in the raw report. |
| Hybrid policy | Replay the exact AI results through the production cache and fallback service using synthetic decks. This measures both AI-only successes and cards rescued by a mix or by deck answers alone. |
| Deck-only | Use the same fallback with no AI candidates and a separate cold cache. This measures what the deck can supply during an outage. |

The replay arms call the actual owner-scoped cache service and verify a second call reuses successful choices. The two arms use separate copies of each synthetic deck. Live inference runs serially with cold cache and measures individual card generation rather than a concurrent session's preparation deadline.

Success rates divide ready cards by 108 for the full dataset or by 12 for each category. Request metrics count initial requests plus retries. Invalid responses are replies rejected by the JSON parser or envelope checker. Candidate rejects are separate counts for individual candidate strings or values. A response can produce more than one reject. A combined shortfall means the fallback could not complete a choice set even when its reported reason reflects the last model outcome. Deck-only uses an injected unavailable service, so its failure code is `ollama_unavailable` even when the underlying deck has too few distinct answers.

## Regression tests

~~~powershell
docker run --rm --network none -e DATABASE_URL=sqlite:////tmp/quality-regression.db queezo-quality-backend python -m pytest -q tests/test_distractors.py tests/test_distractor_cache.py tests/test_multiple_choice.py tests/test_study.py tests/test_scheduler.py
~~~
