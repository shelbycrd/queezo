<script setup>
import {computed} from 'vue';
import AchievementBadge from './AchievementBadge.vue';
import {achievementProgress, sortedAchievements, unlockedDate} from '../services/achievements.js';

defineEmits(['close']);

// Owners receive every achievement with progress; visitors receive unlocked ones only.
const {achievements, owner} = defineProps({achievements:{type:Array,default:() => []}, owner:Boolean});
const items = computed(() => sortedAchievements(achievements).map(item => ({
  ...item, progressInfo:owner ? achievementProgress(item) : null, earned:owner ? unlockedDate(item) : '',
})));
const earnedCount = computed(() => items.value.filter(item => item.unlocked).length);
</script>

<template>
  <div class="dialog-heading">
    <h2 id="profile-achievements-heading">Achievements</h2>
    <span v-if="owner" class="badge" :aria-label="earnedCount + ' of ' + items.length + ' earned'">{{ earnedCount }} / {{ items.length }}</span>
    <button type="button" class="secondary small flat-button" aria-label="Close achievements" autofocus @click="$emit('close')">×</button>
  </div>
  <ul class="achievement-list">
    <li v-for="item in items" :key="item.key" class="achievement-item" :class="{locked:!item.unlocked}">
      <AchievementBadge :name="item.key" :unlocked="item.unlocked"/>
      <div class="achievement-copy">
        <h3>{{ item.name }}<span class="sr-only">{{ item.unlocked ? ' (earned)' : ' (locked)' }}</span></h3>
        <p class="achievement-description">{{ item.description }}</p>
        <p v-if="item.earned" class="achievement-meta">Earned {{ item.earned }}</p>
        <template v-else-if="item.progressInfo">
          <progress class="achievement-progress" :value="item.progressInfo.value" :max="item.progressInfo.goal"
            :aria-label="item.name + ' progress'" :aria-valuetext="item.progressInfo.label"></progress>
          <p class="achievement-meta">{{ item.progressInfo.label }}<template v-if="item.scope === 'daily'"> · resets daily</template></p>
        </template>
      </div>
    </li>
  </ul>
</template>
