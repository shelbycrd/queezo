import test from 'node:test';
import assert from 'node:assert/strict';
import {insertList, renderCardContent, renderText, safeImageUrl, studyShortcut} from '../js/card-content.js';

test('card text renders ordered/unordered lists and never executes user HTML', () => {
  const rendered = renderText('A question\nsecond line\n\n- First\n- <img src=x onerror=alert(1)>\n\n1. One\n2. Two');
  assert.equal(rendered, '<p>A question<br>second line</p><ul><li>First</li><li>&lt;img src=x onerror=alert(1)&gt;</li></ul><ol><li>One</li><li>Two</li></ol>');
  assert.ok(!rendered.includes('<img'));
});

test('only bounded raster data URLs can be used as card photos', () => {
  const source = 'data:image/png;base64,aGVsbG8=';
  assert.equal(safeImageUrl(source), source);
  for (const invalid of ['https://example.com/x.png', 'javascript:alert(1)', 'data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,abc', source + '" onload="bad', `data:image/png;base64,${'A'.repeat(2200000)}`]) {
    assert.equal(safeImageUrl(invalid), '');
    assert.ok(!renderCardContent('Question', invalid).includes('<img'));
  }
});

test('image alt text is escaped and a safe image remains separate from text HTML', () => {
  const rendered = renderCardContent('<script>x</script>', 'data:image/png;base64,aGVsbG8=', '" onerror="bad');
  assert.ok(rendered.includes('&lt;script&gt;x&lt;/script&gt;'));
  assert.ok(rendered.includes('alt="&quot; onerror=&quot;bad"'));
});

test('list controls affect selected lines, preserve surrounding text, and replace old markers', () => {
  assert.deepEqual(insertList('alpha\nbeta\ngamma', 7, 9), {value:'alpha\n- beta\ngamma', start:6, end:12});
  assert.equal(insertList('- alpha\n- beta', 0, 14, true).value, '1. alpha\n2. beta');
  assert.equal(insertList('', 0, 0).value, '- ');
  assert.equal(insertList('\nExisting text', 0, 0).value, '- \nExisting text');
});

test('Enter only reveals, while 1/2/3 select rating shortcuts and held/modified keys do nothing', () => {
  assert.equal(studyShortcut({key:'Enter'}), 'reveal');
  assert.equal(studyShortcut({key:'1'}), 'hard');
  assert.equal(studyShortcut({key:'2'}), 'normal');
  assert.equal(studyShortcut({key:'3'}), 'easy');
  for (const event of [{key:'4'}, {key:'1',repeat:true}, {key:'Enter',ctrlKey:true}, {key:'2',isComposing:true}]) assert.equal(studyShortcut(event), null);
});
