# Phase 4A findings

The benchmark evaluated 108 synthetic cards with generation version 2 and seed 42. The live run used local Ollama 0.40.16 with `qwen3:1.7b`. Live and mocked runs both include the targeted Unicode fix. [Live evidence](results/live.json) · [Mocked evidence](results/mock.json) · [Reproduction commands](README.md)

## Structural readiness

Each cell shows ready cards out of 108. Readiness requires three distractors distinct after the application's normalization, excluding the stored Back.

| Policy | Live AI replay | Mocked transport |
| --- | ---: | ---: |
| AI-only | 106/108 (98.1%) | 36/108 (33.3%) |
| AI-first hybrid policy | 107/108 (99.1%) | 97/108 (89.8%) |
| Deck-only | 80/108 (74.1%) | 80/108 (74.1%) |

The live hybrid policy kept 106 all-AI sets and rescued one card using deck answers alone. It produced zero mixed-source sets in this run. The scripted fixture explicitly exercised mixed cases. There were 34 mixed sets, 27 deck-only rescues and 36 all-AI sets among the 97 mocked hybrid-policy successes. The deck-only arm measures capacity during an outage, so both runs use the same answers.

| Category | Live AI-only | Live hybrid policy | Deck-only |
| --- | ---: | ---: | ---: |
| Definitions | 12/12 | 12/12 | 12/12 |
| Acronyms | 12/12 | 12/12 | 12/12 |
| Programming | 12/12 | 12/12 | 12/12 |
| Operating systems | 12/12 | 12/12 | 12/12 |
| Mathematics | 12/12 | 12/12 | 12/12 |
| True/False | 12/12 | 12/12 | 0/12 |
| Repeated answers | 12/12 | 12/12 | 0/12 |
| Unfamiliar terminology | 12/12 | 12/12 | 12/12 |
| Gibberish | 10/12 | 11/12 | 8/12 |

### Model responses and rejection counts

| Metric | Live | Mocked |
| --- | ---: | ---: |
| Generation requests | 120 | 252 |
| Additional retry requests | 12 | 144 |
| Cards requiring retries | 9 | 72 |
| Literal-format retry requests | 5 | 6 |
| Invalid JSON or response envelopes | 0 | 72 |
| Requests without response headers | 0 | 36 |
| Candidate values received | 678 | 792 |
| Duplicate candidate values rejected | 36 across 19 cards | 198 across 72 cards |
| Candidate values matching the correct Back | 56 across 21 cards | 126 across 72 cards |
| Other rejected values | 23 format mismatches | 252 blanks/non-text and 18 invalid Unicode strings |
| AI runs ending in `insufficient_distractors` | 2 | 36 |
| Shortfalls after AI-first hybrid fallback | 1 | 11 |
| Shortfalls with deck answers alone | 28 | 28 |

The original four-card keyboard-mash repro prepared 3/4 in the seeded live run. For `gibberish-1-02`, all 13 candidates across three requests repeated the Back. The deck supplied only two eligible alternatives. `gibberish-2-03` rejected 18 format-mismatched model choices, then prepared using three distinct same-deck alternatives. Its accepted deck options included the Front text itself. The deterministic regression for the four-card repro separately demonstrates all four preparing when each gets one usable AI choice.

## Semantic review

The [preliminary review](sample-review.csv) applies the [human-review rubric](REVIEW_RUBRIC.md) to 42 captured distractors across all nine categories. This was assistant-assisted inspection of selected examples. Independent human review remains pending, and the sample was selected to cover failure modes rather than estimate whole-dataset accuracy. The third row below is the single live rescue, which happened to use deck answers only.

| Reviewed set | Choices | Plausibility 2 / 1 / 0 | Ambiguous | Potentially correct or uncertain |
| --- | ---: | ---: | ---: | ---: |
| AI-only | 33 | 19 / 10 / 4 | 5 | 2 potentially correct, 3 uncertain |
| Deck-only baseline | 6 | 0 / 1 / 5 | 0 | 0 |
| Live hybrid-policy rescue | 3 | 1 / 2 / 0 | 0 | Literal text, factual rating not applicable |

- **Accepted synonyms.** “Task switch” could earn credit for the description of a context switch. “Passive transport” and “Diffusion” were reasonable broader descriptions in the osmosis item and were flagged for adjudication.
- **Binary format.** The True/False category reached 12/12 structural readiness. Only the opposite truth value is a valid distractor in a conventional binary item. The sampled model also supplied a sentence logically equivalent to the expected True answer.
- **Answer-form and topic mismatch.** An AI distractor of `3/6` equals `1/2` but fails the stated lowest-terms requirement. The deck proposed `1/2` to a question requiring a percentage and unrelated biology and physics terms for an evaporation question.
- **Literal matching.** Similar visible form can be judged for arbitrary strings, while factual plausibility is undefined. A candidate identical to a card's Front can still pass the current text filter.

## Confirmed defect and fix

A mocked Ollama response containing a lone surrogate escape and a valid candidate crashed before the second HTTP request. The JSON parser accepted the escaped value, and the generator carried it into the retry payload, which could not encode it as UTF-8. A previously cached value of that form could also be served.

The generator now rejects lone surrogates before retaining them or adding rejection examples to future prompts, and cache validation regenerates affected entries. Valid Unicode and partial candidates remain usable. The existing cache version and generation strategy were retained. No app route, timing flow or Classic scheduler change was needed.

New regressions cover the retry crash, recovery from a malformed cached choice and successful hybrid preparation of the exact four-card reproduction. The 270-test backend run covered the generator, cache, Multiple-Choice sessions, Classic study and scheduling. The mocked benchmark also reproduced byte-for-byte.

## Limits of this evaluation

The live numbers are one seeded run on one model/runtime combination. Rates depend on the chosen question mix and deck grouping, especially the True/False and repeated-answer decks. The live benchmark sampled individual cold calls and does not measure concurrent deck preparation or its overall deadline. Structural filters detect exact textual collisions and malformed text. They cannot decide factual equivalence, valid alternate names, or whether the distractors teach the intended distinction.
