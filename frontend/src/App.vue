<script setup>
import {computed, inject, nextTick, onScopeDispose, ref, watch} from 'vue';
import {RouterView, useRoute} from 'vue-router';
import {backIcon} from './services/format.js';
import {account} from './services/session.js';
import {avatarUrl} from './services/profiles.js';
import {showNotice} from './services/notice.js';
import {studyRequest, closeStudyOptions} from './services/study-dialog.js';
import {useEvent} from './composables/lifecycle.js';
import {setPomodoroUser, startPomodoroClock, timerState, timerText, timerAlert, latestAlert, dismissTimerAlert} from './services/pomodoro.js';
import {friendsOpen, openFriends, closeFriends} from './services/friends.js';
import {buttonFeedback as vButtonFeedback} from './components/ButtonFeedback.js';
import FriendsDrawer from './components/FriendsDrawer.vue';
import NoticePopup from './components/NoticePopup.vue';
import StudyOptions from './components/StudyOptions.vue';

const route = useRoute(), auth = inject('auth');
const accountMenu = ref(), main = ref(), notifications = ref();
const notificationOpen = ref(false), loggingOut = ref(false);
const navTimer = computed(() => timerState.value.running ? 'Pomodoro · ' + timerText.value : 'Pomodoro');
const section = computed(() => route.meta.nav || route.name);
const back = computed(() => route.meta.back?.(route));
const scopeKey = computed(() => (account.value?.id || 'guest') + ':' + route.path);
onScopeDispose(startPomodoroClock());
watch(() => route.meta.studyFocus, focused => {
  document.body.classList.toggle('study-focus', Boolean(focused));
}, {immediate:true});
onScopeDispose(() => document.body.classList.remove('study-focus'));
watch(() => account.value?.id, id => {
  document.body.classList.toggle('signed-in', Boolean(id));
  setPomodoroUser(id ?? null);
  closeFriends(); closeStudyOptions(); notifications.value?.close();
}, {immediate:true, flush:'sync'});
watch(() => route.path, async () => {
  closeFriends(); closeStudyOptions(); showNotice('');
  if (accountMenu.value) accountMenu.value.open = false;
  await nextTick();
  window.scrollTo(0,0);
  // Preserve intentional dialog or editor autofocus after route changes.
  if (!main.value?.contains(document.activeElement) && !document.querySelector('dialog[open]')) main.value?.focus({preventScroll:true});
});
watch([() => route.meta.title, navTimer], ([title]) => {
  document.title = 'Queezo • ' + (route.name === 'pomodoro' && timerState.value.running ? timerText.value : title || 'Page not found');
}, {immediate:true});
function toggleNotifications() {
  if (notifications.value.open) notifications.value.close();
  else { notifications.value.show(); notificationOpen.value = true; }
}
watch(friendsOpen, opened => { if (opened) notifications.value?.close(); });
function closeFromAction(event) {
  if (event.target.closest('.account-menu a,.account-menu button')) accountMenu.value.open = false;
}
useEvent(document, 'click', event => {
  if (accountMenu.value && !accountMenu.value.contains(event.target)) accountMenu.value.open = false;
  if (notifications.value?.open && !notifications.value.contains(event.target) && !event.target.closest('#open-notifications')) notifications.value.close();
});
useEvent(document, 'keydown', event => {
  if (event.key !== 'Escape') return;
  if (accountMenu.value?.open) {
    accountMenu.value.open = false;
    accountMenu.value.querySelector('summary')?.focus();
  }
  if (notifications.value?.open) {
    notifications.value.close();
    document.getElementById('open-notifications')?.focus();
  }
});
async function logout() {
  if (loggingOut.value) return;
  loggingOut.value = true;
  try { await auth.logout(); } finally { loggingOut.value = false; }
}
</script>
<template>
  <div class="ambient-shapes" aria-hidden="true">
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape snowflake" viewBox="0 0 40 40"><path d="M20 3v34M5.3 11.5l29.4 17M5.3 28.5l29.4-17M15 7l5 5 5-5M15 33l5-5 5 5M7 17l7-2-2-7M28 32l-2-7 7-2M7 23l7 2-2 7M28 8l-2 7 7 2"/></svg>
    <svg class="ambient-shape star" viewBox="0 0 40 40"><path d="m20 3 5.3 10.8 11.9 1.7-8.6 8.4 2 11.8L20 30.1 9.4 35.7l2-11.8-8.6-8.4 11.9-1.7Z"/></svg>
    <svg class="ambient-shape droplet" viewBox="0 0 40 40"><path d="M20 3C17 10 8 19 8 26a12 12 0 0 0 24 0C32 19 23 10 20 3Z"/><ellipse cx="17" cy="22" rx="4" ry="6" fill="white" opacity=".65"/></svg>
  </div>
  <header class="site-header" v-button-feedback>
    <a class="brand" href="/#/dashboard" aria-label="Queezo home"><img class="brand-cloud" src="/assets/queezo-cloud.svg" alt="" width="80" height="80"><span class="brand-name">Queezo</span></a>
    <nav id="main-navigation" aria-label="Main navigation" v-show="account">
      <a href="/#/dashboard" data-nav="dashboard" :aria-current="section === 'dashboard' ? 'page' : undefined"><span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/></svg></span>Home</a>
      <a href="/#/decks" data-nav="decks" :aria-current="section === 'decks' ? 'page' : undefined"><span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="6" y="6" width="15" height="15" rx="3"/><path d="M17 3H6a3 3 0 0 0-3 3v11M10 11h7m-7 4h4"/></svg></span>Flashcards</a>
      <a href="/#/gwa" data-nav="gwa" :aria-current="section === 'gwa' ? 'page' : undefined"><span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M8 7h8m-8 5h2m4 0h2m-8 4h2m4 0h2"/></svg></span>GWA Calculator</a>
      <a href="/#/pomodoro" data-nav="pomodoro" :aria-current="section === 'pomodoro' ? 'page' : undefined"><span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="13" r="8"/><path d="M9 2h6m-3 0v3m0 4v5l3 2"/></svg></span><span id="pomodoro-nav-label">{{ navTimer }}</span></a>
    </nav>
    <a class="sidebar-settings" href="/#/settings" data-nav="settings" :aria-current="section === 'settings' ? 'page' : undefined"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3z"/><circle cx="12" cy="12" r="3"/></svg>Settings</a>
  </header>
  <div v-button-feedback id="account-controls" class="account-controls" v-show="account"><button id="open-friends" aria-haspopup="dialog" aria-controls="friends-drawer" :aria-expanded="friendsOpen" @click="openFriends" type="button" class="topbar-icon secondary flat-button" aria-label="Open friends"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5v2"/></svg></button><button id="open-notifications" :aria-expanded="notificationOpen" aria-haspopup="dialog" aria-controls="notifications-panel" @click="toggleNotifications" type="button" class="topbar-icon secondary flat-button" aria-label="Open notifications"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 20h4"/></svg></button><details id="account-dropdown" ref="accountMenu" @click="closeFromAction"><summary class="account-trigger"><img class="account-avatar" id="account-avatar" :src="avatarUrl(account?.avatar)" alt="" width="32" height="32"><span id="account-email">{{ account?.display_name || account?.username || account?.email?.split('@')[0] }}</span><span aria-hidden="true">⌄</span></summary><div class="account-menu"><a href="/#/profile">Profile</a><a href="/#/help">Help</a><button id="logout" type="button" :disabled="loggingOut" @click="logout">Log out</button></div></details></div>
  <aside id="pomodoro-alert" v-button-feedback class="pomodoro-alert" aria-label="Pomodoro notification" :hidden="!timerAlert">
    <div role="status" aria-live="polite"><strong>{{ latestAlert?.title }}</strong><p>{{ latestAlert?.message }}</p></div>
    <div class="actions"><a href="/#/pomodoro">Open timer</a><button type="button" class="secondary small" id="dismiss-pomodoro-alert" aria-label="Dismiss timer notification" @click="dismissTimerAlert">Dismiss</button></div>
  </aside>
  <main id="app" ref="main" tabindex="-1" v-button-feedback :class="{'has-subpage-back':back || route.name === 'study' || route.name === 'summary'}">
    <a v-if="back" class="subpage-back" :href="back" aria-label="Go back" v-html="backIcon"></a>
    <RouterView v-slot="{Component}"><component :is="Component" :key="scopeKey" /></RouterView>
  </main>
  <FriendsDrawer/>
  <Teleport to="body">
    <dialog id="notifications-panel" ref="notifications" v-button-feedback aria-label="Notifications" @close="notificationOpen = false">
      <div class="drawer-heading"><h2>Notifications</h2><button class="secondary small flat-button" aria-label="Close notifications" @click="notifications.close()">×</button></div>
      <article v-if="latestAlert"><h3>{{ latestAlert.title }}</h3><p>{{ latestAlert.message }}</p><a href="/#/pomodoro" @click="notifications.close()">Open timer</a></article>
      <div v-else class="notifications-empty"><h3>You’re all caught up</h3><p>Timer updates will appear here.</p></div>
    </dialog>
  </Teleport>
  <StudyOptions v-if="studyRequest" :request="studyRequest"/>
  <NoticePopup/>
</template>
