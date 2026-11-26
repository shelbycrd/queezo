<script setup>
import {computed} from 'vue';
import AchievementBadge from './AchievementBadge.vue';
import {achievementProgress, sortedAchievements, unlockedDate} from '../services/achievements.js';

// Owners receive every achievement with progress; visitors receive unlocked ones only.
const {achievements, owner} = defineProps({achievements:{type:Array,default:() => []}, owner:Boolean});
const items = computed(() => sortedAchievements(achievements).map(item => ({
  ...item, progressInfo:owner ? achievementProgress(item) : null, earned:owner ? unlockedDate(item) : '',
})));
const earnedCount = computed(() => items.value.filter(item => item.unlocked).length);
</script>

<template>
  <section v-if="owner || items.length" class="panel profile-section profile-achievements" aria-labelledby="profile-achievements-heading">
    <div class="profile-section-heading"><h2 id="profile-achievements-heading">Achievements</h2>
      <span v-if="owner" class="badge">{{ earnedCount }} / {{ items.length }}</span></div>
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
  </section>
</template>
