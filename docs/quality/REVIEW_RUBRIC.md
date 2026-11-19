# Semantic review rubric

Review the Front, the stored Back, and each displayed distractor as a learner would see them. Use the [dataset](flashcards.json) and the choice positions in [live results](results/live.json). The same option can receive different scores on different questions. For a blind review, hide the source arm and shuffle the option order, then record the original choice position for reproducibility.

## Per-choice ratings

| Field | Rating | Criteria |
| --- | --- | --- |
| Plausibility | 2 | Same answer type and topic. A learner could reasonably pick it while confusing related concepts. |
| Plausibility | 1 | Related, but weak, too broad or narrow, or mismatched in answer form. |
| Plausibility | 0 | Unrelated, clearly absurd, or violates an explicit constraint such as True/False. |
| Ambiguity | yes / no | Mark yes if the prompt, correct answer, or distractor allows an alternative reasonable reading that changes what should earn credit. |
| Potentially correct | yes / no / uncertain / n/a | Mark yes for an equivalent value, accepted synonym, valid alternative name, or another answer that satisfies the wording. Mark uncertain when the reviewer cannot resolve it from the wording or available expertise. Use n/a for cards intended as literal arbitrary strings without a factual claim. |

For an invented literal answer, judge plausibility by visual form, character style, and length. For factual invented scenarios, use only the facts given in that scenario. For math, check equivalence and respect explicit form requirements. For definitions and technical names, check accepted variants in context. An option can earn high plausibility and still fail review because it is another correct answer. A binary question with three extra options can have perfectly unique strings yet still fail format plausibility.

## Recording and decision

Record card ID, arm, one-based option position in the report's distractor array, the three ratings, and a short rationale. Check for unintended multiple correct answers at the question level. Flag any yes or uncertain correctness rating, and flag sets with an ambiguity or with fewer than two plausible choices. This is a review threshold, not a release claim.

The checked-in sample is an assistant-assisted rubric walkthrough. It is not an independent human panel, a representative survey, or a semantic accuracy percentage for all generated distractors. A human reviewer can use the same fields, flag disagreements, and resolve uncertain calls without relying on the application's normalized text checks.
