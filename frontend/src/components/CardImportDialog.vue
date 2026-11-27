<script setup>
import {computed, nextTick, ref} from 'vue';
import {api} from '../../js/api.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import {buttonFeedback as vButtonFeedback} from './ButtonFeedback.js';
import CopyButton from './CopyButton.vue';
import {DECK_CARD_LIMIT, IMPORT_TEXT_LIMIT, MAX_IMPORT_BYTES, MAX_LISTED_ERRORS, SAMPLE_IMPORT, describeImportError, isJsonFile, parseCardImport} from '../services/card-import.js';

// Imports run as one all-or-nothing request; the server validates everything again.
const {deckId, count} = defineProps({deckId:{type:String,required:true}, count:{type:Number,default:0}});
const emit = defineEmits(['imported','refresh']);
const {active} = useLifetime();
const dialog = ref(), textarea = ref(), fileInput = ref(), tabs = ref([]);
const tab = ref('import'), text = ref(''), fileName = ref(''), dragging = ref(false);
const pending = ref(false), serverError = ref(''), touched = ref(false);
let importId = null;

const room = computed(() => Math.max(0, DECK_CARD_LIMIT - count));
const result = computed(() => parseCardImport(text.value, room.value));
const errors = computed(() => serverError.value ? [serverError.value] : touched.value ? result.value.errors : []);
const shownErrors = computed(() => errors.value.slice(0, MAX_LISTED_ERRORS));
const ready = computed(() => result.value.cards.length);

function open() {
  text.value = ''; fileName.value = ''; serverError.value = ''; touched.value = false; importId = null;
  tab.value = 'import'; dragDepth = 0; dragging.value = false;
  dialog.value.showModal();
  void nextTick(() => textarea.value?.focus());
}
defineExpose({open});

function edited() {
  touched.value = Boolean(text.value.trim());
  serverError.value = '';
  importId = null; // Different content is a different import.
}

async function load(file) {
  serverError.value = '';
  if (!file) return;
  if (!isJsonFile(file)) { touched.value = true; serverError.value = 'Choose a .json file.'; return; }
  if (file.size > MAX_IMPORT_BYTES) { touched.value = true; serverError.value = 'This file is larger than 512 KB. Split it into smaller imports.'; return; }
  try {
    const content = await file.text();
    if (!active()) return;
    text.value = content; fileName.value = file.name;
    edited();
  } catch { touched.value = true; serverError.value = 'This file could not be read.'; }
}
function chooseFile(event) {
  void load(event.target.files?.[0]);
  event.target.value = '';
}
let dragDepth = 0; // Child elements fire their own enter/leave events while dragging over the zone.
function dragEnter() { dragDepth += 1; dragging.value = true; }
function dragLeave() { dragDepth = Math.max(0, dragDepth - 1); dragging.value = dragDepth > 0; }
function drop(event) {
  dragDepth = 0;
  dragging.value = false;
  void load(event.dataTransfer?.files?.[0]);
}

function selectTab(name, focus = false) {
  tab.value = name;
  if (focus) void nextTick(() => tabs.value[name === 'import' ? 0 : 1]?.focus());
}
function tabKey(event) {
  const order = ['import','format'];
  const index = order.indexOf(tab.value);
  const next = {ArrowRight:index + 1, ArrowLeft:index - 1, Home:0, End:order.length - 1}[event.key];
  if (next === undefined) return;
  event.preventDefault();
  selectTab(order[(next + order.length) % order.length], true);
}

async function submit() {
  touched.value = true;
  if (pending.value || !ready.value) return;
  pending.value = true;
  serverError.value = '';
  importId ??= crypto.randomUUID(); // Reused if the same content is retried, so the server can refuse a duplicate.
  try {
    const saved = await api('/decks/' + encodeURIComponent(deckId) + '/cards/import',
      {method:'POST', body:{import_id:importId, cards:result.value.cards}});
    if (!active()) return;
    emit('imported', saved.cards);
    showNotice(`Imported ${saved.imported} flashcard${saved.imported === 1 ? '' : 's'}.`, true);
    dialog.value.close();
  } catch (error) {
    if (!active()) return;
    if (error.status === 409 && /already saved/.test(error.message)) {
      emit('refresh');
      showNotice('These flashcards were already imported.', true);
      dialog.value.close();
      return;
    }
    serverError.value = describeImportError(error.message);
  } finally { if (active()) pending.value = false; }
}
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" v-button-feedback class="card-import-dialog" aria-labelledby="card-import-title" @cancel="pending && $event.preventDefault()">
      <div class="dialog-heading"><h2 id="card-import-title">Import JSON</h2>
        <button type="button" class="secondary small flat-button" aria-label="Close import" :disabled="pending" @click="dialog.close()">×</button></div>
      <div class="card-import-tabs" role="tablist" aria-label="Import options" @keydown="tabKey">
        <button v-for="(item, index) in [{id:'import',label:'Import JSON'},{id:'format',label:'JSON Format'}]" :key="item.id"
          :ref="element => { tabs[index] = element; }" :id="'card-import-tab-' + item.id" type="button" role="tab"
          :aria-selected="tab === item.id" :aria-controls="'card-import-panel-' + item.id" :tabindex="tab === item.id ? 0 : -1"
          @click="selectTab(item.id)">{{ item.label }}</button>
      </div>

      <form v-show="tab === 'import'" id="card-import-panel-import" role="tabpanel" aria-labelledby="card-import-tab-import" novalidate @submit.prevent="submit">
        <div class="card-import-drop" :class="{dragging}" @dragenter.prevent="dragEnter" @dragover.prevent
          @dragleave="dragLeave" @drop.prevent="drop">
          <label for="card-import-text">Paste JSON, or drop a .json file here</label>
          <textarea id="card-import-text" ref="textarea" v-model="text" spellcheck="false" autocomplete="off" :disabled="pending"
            placeholder='{ "cards": [ { "front": "Question", "back": "Answer" } ] }' aria-describedby="card-import-help card-import-status"
            @input="edited"></textarea>
          <div class="card-import-file">
            <input id="card-import-file" ref="fileInput" class="sr-only" type="file" accept=".json,application/json" :disabled="pending" @change="chooseFile">
            <button type="button" class="secondary small flat-button" :disabled="pending" @click="fileInput.click()">Choose file…</button>
            <span v-if="fileName" class="muted">{{ fileName }}</span>
          </div>
        </div>
        <p id="card-import-help" class="hint">Up to 512 KB · {{ room }} of 150 card slots left · {{ IMPORT_TEXT_LIMIT }} characters per side · Text only</p>
        <div id="card-import-status" role="status" aria-live="polite">
          <div v-if="shownErrors.length" class="inline-error card-import-errors">
            <ul><li v-for="message in shownErrors" :key="message">{{ message }}</li></ul>
            <p v-if="errors.length > shownErrors.length">…and {{ errors.length - shownErrors.length }} more.</p>
          </div>
          <p v-else-if="ready" class="card-import-preview">Ready to import <strong>{{ ready }}</strong> flashcard{{ ready === 1 ? '' : 's' }}. {{ ready === 1 ? 'It' : 'They' }} will be added after your existing cards.</p>
        </div>
        <div class="actions card-import-actions">
          <button type="button" class="secondary flat-button" :disabled="pending" @click="dialog.close()">Cancel</button>
          <button type="submit" :disabled="pending || !ready">{{ pending ? 'Importing…' : ready ? `Import ${ready} card${ready === 1 ? '' : 's'}` : 'Import' }}</button>
        </div>
      </form>

      <section v-show="tab === 'format'" id="card-import-panel-format" role="tabpanel" aria-labelledby="card-import-tab-format" tabindex="0">
        <p class="muted">Use an object with a <code>cards</code> list. Each card needs a non-empty <code>front</code> (question) and <code>back</code> (answer). No other fields are allowed.</p>
        <pre class="card-import-sample"><code>{{ SAMPLE_IMPORT }}</code></pre>
        <div class="actions"><CopyButton :value="SAMPLE_IMPORT">Copy</CopyButton></div>
        <ul class="hint card-import-rules">
          <li>Up to 150 cards per deck, 250 characters per side, and 512 KB per import.</li>
          <li>Text only: links and photos are not accepted, and any HTML is shown as plain text.</li>
          <li>Multiple-Choice answers are prepared the first time you study the cards.</li>
        </ul>
      </section>
    </dialog>
  </Teleport>
</template>
