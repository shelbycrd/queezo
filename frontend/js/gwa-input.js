// Only a complete, valid three-digit shorthand is rewritten while typing.
export function normalizeGradeInput(value) {
  const text = String(value);
  if (/^[1-5]\d{2}$/.test(text) && Number(text) <= 500) return (Number(text) / 100).toFixed(2);
  return text;
}

export function formatGradeDisplay(value) {
  const text = normalizeGradeInput(value);
  if (!text.trim()) return text;
  const number = Number(text);
  if (!Number.isFinite(number) || number < 1 || number > 5) return text;
  // Preserve intentional precision; formatting must not affect classification.
  return /^\d+(?:\.\d{0,2})?$/.test(text) ? number.toFixed(2) : text;
}
