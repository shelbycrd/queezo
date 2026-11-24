<script setup>
import {ref} from 'vue';
import {useRouter} from 'vue-router';
import {api} from '../../js/api.js';
import {useResource} from '../composables/lifecycle.js';
import {showNotice} from '../services/notice.js';
import {chooseSharedStudy} from '../services/study-dialog.js';
import CardContent from '../components/CardContent.vue';
import ResourceState from '../components/ResourceState.vue';

const {token} = defineProps({token:String});
const router = useRouter();
const path = '/shared/decks/' + encodeURIComponent(token);
const {data:deck,error,active} = useResource(signal => api(path,{signal}));
const pending = ref(false);
async function copy() {
  if (pending.value) return;
  pending.value = true;
  try {
    const created = await api(path + '/copy',{method:'POST'});
    if (active()) await router.push('/deck/' + created.id);
  } catch (failure) { if (active()) showNotice(failure.message); }
  finally { pending.value = false; }
}
</script>
<template>
  <ResourceState v-if="!deck" :error="error"/>
  <div v-else class="deck-workspace"><div class="page-heading"><div><span class="badge">{{ deck.visibility === 'public' ? 'Public' : 'Unlisted' }} deck</span><h1>{{ deck.title }}</h1><p class="muted">{{ deck.cards.length }} cards</p></div>
    <div class="actions" :aria-busy="pending"><button id="copy-shared" class="secondary" :disabled="pending" @click="copy()">Save private copy</button><button id="study-shared" :disabled="pending || !deck.cards.length" @click="chooseSharedStudy(token)">Study</button></div></div>
    <div class="card-list"><article v-for="(card,index) in deck.cards" :key="index" class="saved-card"><span class="content-label">Card {{ index + 1 }}</span><CardContent :text="card.front" :image="card.front_image" alt="Question photo"/>
      <details class="shared-answer"><summary>Reveal answer</summary><CardContent :text="card.back" :image="card.back_image" alt="Answer photo"/></details></article>
      <div v-if="!deck.cards.length" class="empty">This deck has no cards yet.</div>
    </div>
  </div>
</template>
