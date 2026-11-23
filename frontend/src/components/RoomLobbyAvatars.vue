<script setup>
import {avatarUrl} from '../services/profiles.js';

defineProps({participants:Array,compact:Boolean});
</script>

<template>
  <ul class="room-lobby-avatars" :class="{compact}" aria-label="Room participants">
    <li v-for="participant in participants" :key="participant.username"
      :class="{ready:participant.ready && participant.connected && !participant.spectator && !participant.host,
        mutedSeat:!participant.host && (!participant.ready || !participant.connected || participant.spectator)}">
      <img :src="avatarUrl(participant.avatar)" alt="" width="54" height="54">
      <strong>{{ participant.display_name }}</strong>
      <small v-if="participant.host" class="badge room-host-badge">Host</small>
      <small v-else>{{ !participant.connected ? 'Disconnected' : participant.spectator ? 'Spectating' : participant.ready ? 'Ready' : 'Not ready' }}</small>
    </li>
  </ul>
</template>
