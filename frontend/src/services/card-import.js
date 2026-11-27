// Client-side checks for JSON flashcard imports. The server repeats every check before saving.
export const IMPORT_TEXT_LIMIT = 250;
export const DECK_CARD_LIMIT = 150;
export const MAX_IMPORT_BYTES = 512 * 1024;
export const MAX_LISTED_ERRORS = 6;

export const SAMPLE_IMPORT = JSON.stringify({cards:[
  {front:'What does CPU stand for?', back:'Central Processing Unit'},
  {front:'What does RAM stand for?', back:'Random Access Memory'},
]}, null, 2);

const isPlainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const sideName = {front:'question (front)', back:'answer (back)'};

export function byteLength(text) {
  return new TextEncoder().encode(text).length;
}

export function isJsonFile(file) {
  return Boolean(file) && (/\.json$/i.test(file.name || '') || file.type === 'application/json');
}

/** Validate pasted or loaded text. Returns {cards, errors}; cards is empty whenever errors exist. */
export function parseCardImport(text, room = DECK_CARD_LIMIT) {
  const fail = (...errors) => ({cards:[], errors});
  if (!text || !text.trim()) return fail('Paste JSON or choose a .json file to import.');
  if (byteLength(text) > MAX_IMPORT_BYTES) return fail('This JSON is larger than 512 KB. Split it into smaller imports.');
  let data;
  try { data = JSON.parse(text); }
  catch (error) { return fail('This is not valid JSON. ' + String(error.message || '').replace(/^JSON\.parse: /,'')); }
  if (!isPlainObject(data)) return fail('The JSON must be an object with a "cards" list, like the JSON Format example.');
  const extra = Object.keys(data).filter(key => key !== 'cards');
  if (extra.length) return fail(`Unsupported field ${quote(extra[0])}. Only "cards" is allowed at the top level.`);
  if (!Array.isArray(data.cards)) return fail('"cards" must be a list of flashcards.');
  if (!data.cards.length) return fail('"cards" is empty. Add at least one flashcard.');

  const errors = [], cards = [];
  data.cards.forEach((item, index) => {
    const label = 'Card ' + (index + 1);
    if (!isPlainObject(item)) { errors.push(`${label} must be an object with "front" and "back".`); return; }
    const unknown = Object.keys(item).filter(key => key !== 'front' && key !== 'back');
    if (unknown.length) errors.push(`${label} has unsupported field ${quote(unknown[0])}. Only "front" and "back" are allowed.`);
    const card = {};
    for (const side of ['front','back']) {
      const value = item[side];
      if (typeof value !== 'string') errors.push(`${label} needs a text ${sideName[side]}.`);
      else if (!value.trim()) errors.push(`${label} has an empty ${sideName[side]}.`);
      else if (Array.from(value.trim()).length > IMPORT_TEXT_LIMIT) errors.push(`${label} ${sideName[side]} is longer than ${IMPORT_TEXT_LIMIT} characters.`);
      else card[side] = value.trim();
    }
    if (card.front && card.back) cards.push(card);
  });
  if (data.cards.length > room) {
    errors.unshift(room > 0
      ? `This deck has room for ${room} more flashcard${room === 1 ? '' : 's'}, but the JSON has ${data.cards.length}.`
      : 'This deck already has 150 flashcards.');
  }
  return errors.length ? {cards:[], errors} : {cards, errors};
}

// Turn server field paths like "body.cards.2.front: Value error, ..." into card-numbered messages.
export function describeImportError(message) {
  return String(message || 'The import could not be saved.')
    .replace(/body\.cards\.(\d+)\.(front|back): (?:Value error, )?/g, (_, index, side) => `Card ${Number(index) + 1} ${sideName[side]}: `)
    .replace(/body\.cards\.(\d+): /g, (_, index) => `Card ${Number(index) + 1}: `);
}

function quote(key) {
  return JSON.stringify(String(key).slice(0, 40));
}
