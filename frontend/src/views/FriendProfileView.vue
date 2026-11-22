<script setup>
import {api} from '../../js/api.js';
import {useResource} from '../composables/lifecycle.js';
import {plural} from '../services/format.js';
import DeckTile from '../components/DeckTile.vue';
import ResourceState from '../components/ResourceState.vue';
const {username} = defineProps({username:String});
const {data:friend,error} = useResource(signal => api('/friends/' + encodeURIComponent(username) + '/profile',{signal}));
</script>
<template>
  <ResourceState v-if="!friend" :error="error"/>
  <template v-else>
    <section class="panel profile-card friend-profile"><div class="profile-avatar" aria-hidden="true">{{ Array.from(friend.display_name.trim())[0]?.toUpperCase() || '?' }}</div>
      <div class="profile-identity"><h1>{{ friend.display_name }}</h1><p class="profile-username">@{{ friend.username }}</p></div>
    </section>
    <section class="profile-public"><div class="section-heading"><h2>Public Decks</h2><span class="deck-total">{{ plural(friend.public_decks.length,'deck') }}</span></div>
      <div v-if="friend.public_decks.length" class="deck-grid"><DeckTile v-for="deck in friend.public_decks" :key="deck.share_token" :deck="deck" shared/></div>
      <p v-else class="empty">No public decks yet.</p>
    </section>
  </template>
</template>
