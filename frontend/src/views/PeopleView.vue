<script setup>
import {ref, watch} from 'vue';
import {api} from '../../js/api.js';
import {avatarUrl,profilePath} from '../services/profiles.js';

const input = ref(''), q = ref(''), results = ref([]), pending = ref(false), error = ref(''), retry = ref(0);
watch([q,retry],async ([term],_,onCleanup) => {
  const request = new AbortController();
  onCleanup(() => request.abort());
  pending.value = true; error.value = '';
  try {
    const records = await api('/profiles/search?' + new URLSearchParams({q:term}),{signal:request.signal});
    if (!request.signal.aborted) results.value = records;
  } catch (failure) { if (!request.signal.aborted) error.value = failure.message; }
  finally { if (!request.signal.aborted) pending.value = false; }
},{immediate:true});
</script>
<template>
  <div class="page-heading"><h1>Find profiles</h1></div>
  <section class="panel account-page">
    <form role="search" class="new-deck-form" @submit.prevent="q = input.trim()"><div><label for="people-query">Search by name or username</label><input id="people-query" v-model="input" type="search" maxlength="80" autocomplete="off"></div><button type="submit" class="secondary flat-button">Search</button></form>
    <p v-if="pending" role="status" class="muted">Searching profiles…</p>
    <div v-else-if="error"><p role="alert">{{ error }}</p><button type="button" class="secondary flat-button" @click="retry++">Retry</button></div>
    <ul v-else-if="results.length" class="profile-people">
      <li v-for="person in results" :key="person.username"><a :href="profilePath(person.username)"><img :src="avatarUrl(person.avatar)" alt="" width="44" height="44"><span><strong>{{ person.display_name }}</strong><br><small>@{{ person.username }}</small></span></a></li>
    </ul>
    <p v-else class="muted">No public profiles found.</p>
  </section>
</template>
