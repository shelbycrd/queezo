const answerKey = answer => answer.trim().replace(/\s+/g, ' ').toLowerCase();

export function sharedAnswers(cards) {
  const answers = new Map();
  for (const {back} of cards) {
    const key = answerKey(back);
    if (key && !answers.has(key)) answers.set(key, back);
  }
  return [...answers.values()];
}

export function shuffle(items, random = Math.random) {
  const result = [...items];
  for (let index = result.length - 1; index > 0; index--) {
    const other = Math.floor(random() * (index + 1));
    [result[index], result[other]] = [result[other], result[index]];
  }
  return result;
}

export function sharedChoices(answer, answers) {
  const key = answerKey(answer);
  const distractors = shuffle(answers.filter(other => answerKey(other) !== key)).slice(0, 3);
  return key && distractors.length === 3 ? shuffle([answer, ...distractors]) : [];
}
