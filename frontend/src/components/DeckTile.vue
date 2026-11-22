<script setup>
import {computed, ref} from 'vue';
import {icon} from '../../js/icons.js';
import {plural} from '../services/format.js';
import {deckColor} from '../services/deck-colors.js';
import {chooseStudy} from '../services/study-dialog.js';
const props = defineProps({deck:Object, shared:Boolean});
const target = computed(() => props.shared ? '/#/shared/' + encodeURIComponent(props.deck.share_token) : '#/deck/' + props.deck.id);
const color = computed(() => deckColor(props.shared ? props.deck.share_token : props.deck.id));
const pending = ref(false);
async function study() {
  pending.value = true;
  try { await chooseStudy(props.deck.id); } finally { pending.value = false; }
}
</script>
<template>
  <article class="deck-card portrait-deck" :class="color">
    <component :is="shared ? 'a' : 'div'" class="deck-cover" :href="shared ? target : undefined" :aria-label="shared ? 'Open ' + deck.title : undefined"><span class="deck-cover-icon" v-html="icon('cards')"></span><span class="deck-cover-lines" aria-hidden="true"></span><span class="deck-cover-label">MADE TO REMEMBER</span></component>
    <div class="deck-card-body"><h2><a v-if="shared" :href="target">{{ deck.title }}</a><template v-else>{{ deck.title }}</template></h2><p class="muted">{{ plural(deck.card_count,'flashcard') }}</p>
      <div class="actions" :aria-busy="pending"><a class="button secondary small flat-button" :href="target">Open deck</a>
        <span v-if="shared" class="badge">Public</span><button v-else class="small" :data-study="deck.id" :disabled="!deck.card_count || pending" @click="study">Study <span v-html="icon('arrow')"></span></button>
      </div>
    </div>
  </article>
</template>
