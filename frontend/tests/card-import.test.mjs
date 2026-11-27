import {test} from 'node:test';
import assert from 'node:assert/strict';
import {MAX_IMPORT_BYTES, SAMPLE_IMPORT, describeImportError, isJsonFile, parseCardImport} from '../src/services/card-import.js';

const json = value => JSON.stringify(value);

test('the documented sample imports as written, trimmed and in order', () => {
  const {cards, errors} = parseCardImport(SAMPLE_IMPORT);
  assert.deepEqual(errors, []);
  assert.deepEqual(cards.map(card => card.front), ['What does CPU stand for?', 'What does RAM stand for?']);
  assert.deepEqual(parseCardImport(json({cards:[{front:'  Q  ', back:'\nA '}]})).cards, [{front:'Q', back:'A'}]);
});

test('syntax and structure problems get specific messages', () => {
  const first = text => parseCardImport(text).errors[0];
  assert.match(first(''), /Paste JSON/);
  assert.match(first('{"cards": [}'), /not valid JSON/);
  assert.match(first('[]'), /object with a "cards" list/);
  assert.match(first(json({cards:[], title:'x'})), /Unsupported field "title"/);
  assert.match(first(json({cards:'nope'})), /must be a list/);
  assert.match(first(json({cards:[]})), /is empty/);
});

test('each card needs non-empty text front and back with no extra fields', () => {
  const {cards, errors} = parseCardImport(json({cards:[
    {front:'Q', back:'A'}, {front:'', back:'A'}, {front:'Q'}, {front:1, back:'A'},
    {front:'Q', back:'A', image:'x'}, 'card', {front:'x'.repeat(251), back:'A'},
  ]}));
  assert.deepEqual(cards, []); // nothing is imported while any card is invalid
  assert.deepEqual(errors, [
    'Card 2 has an empty question (front).', 'Card 3 needs a text answer (back).', 'Card 4 needs a text question (front).',
    'Card 5 has unsupported field "image". Only "front" and "back" are allowed.', 'Card 6 must be an object with "front" and "back".',
    'Card 7 question (front) is longer than 250 characters.',
  ]);
  assert.equal(parseCardImport(json({cards:[{front:'😀'.repeat(250), back:'A'}]})).errors.length, 0); // counts characters
});

test('deck capacity and file size are enforced before sending', () => {
  const three = json({cards:[1,2,3].map(n => ({front:'Q' + n, back:'A'}))});
  assert.match(parseCardImport(three, 2).errors[0], /room for 2 more flashcards, but the JSON has 3/);
  assert.match(parseCardImport(three, 0).errors[0], /already has 150/);
  assert.equal(parseCardImport(three, 3).cards.length, 3);
  assert.match(parseCardImport(' '.repeat(MAX_IMPORT_BYTES) + '{}').errors[0], /larger than 512 KB/);
});

test('files are recognised by extension or type, and server errors name the card', () => {
  assert.equal(isJsonFile({name:'deck.JSON', type:''}), true);
  assert.equal(isJsonFile({name:'deck', type:'application/json'}), true);
  assert.equal(isJsonFile({name:'deck.txt', type:'text/plain'}), false);
  assert.equal(describeImportError('body.cards.1.front: Value error, URL links are not allowed in deck titles, questions, or answers.'),
    'Card 2 question (front): URL links are not allowed in deck titles, questions, or answers.');
});
