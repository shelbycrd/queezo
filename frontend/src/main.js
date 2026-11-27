import {createApp} from 'vue';
import {createRouter, createWebHistory} from 'vue-router';
import App from './App.vue';
import {account, initAuthentication, loginMessage} from './services/session.js';
import {showNotice} from './services/notice.js';
import {internalLinkPath, legacyHashPath, setRouter} from './services/navigation.js';
import '../css/styles.css';
import '../css/pomodoro.css';
import '../css/auth.css';
import '../css/theme.css';
import '../css/cloud-theme.css';
import '../css/multiple-choice.css';
import '../css/profiles.css';
import '../css/study-rooms.css';
import '../css/schedule.css';
import '../css/top-bar.css';

// Convert old `/#/page` bookmarks (and `/#shared/token` links) to clean URLs before the router reads the location.
const legacy = legacyHashPath(location.pathname, location.hash);
if (legacy) history.replaceState(null, '', legacy);

const page = (path, name, component, title, options = {}) => ({path, name, component, ...options, meta:{title,...options.meta}});
const deck = () => import('./views/DeckView.vue');
const auth = () => import('./views/AuthView.vue');
const accountPage = () => import('./views/AccountView.vue');
const profile = () => import('./views/ProfileView.vue');
const router = createRouter({history:createWebHistory(), routes:[
  {path:'/', redirect:'/home'},
  // Earlier path names stay as redirects so bookmarks keep working.
  {path:'/dashboard', redirect:'/home'},
  {path:'/decks/:create(new)?', redirect:to => '/flashcards' + (to.params.create ? '/new' : '')},
  {path:'/gwa', redirect:'/gwa-calculator'},
  page('/login','login',auth,'Log in'),
  page('/signup','signup',auth,'Sign up',{props:{signup:true}}),
  page('/home','dashboard',() => import('./views/DashboardView.vue'),'Home'),
  page('/flashcards/:create(new)?','decks',() => import('./views/DecksView.vue'),'Flashcard',{props:true}),
  page('/deck/:deckId(\\d+)/:action(add)?','deck',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => r.params.action ? '/deck/' + r.params.deckId : '/flashcards'}}),
  page('/deck/:deckId(\\d+)/edit/:cardId(\\d+)','edit',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => '/deck/' + r.params.deckId}}),
  page('/deck/:deckId(\\d+)/page/:pageNumber(\\d+)','deck-page',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => '/deck/' + r.params.deckId}}),
  page('/shared/:token([A-Za-z0-9_-]{32,64})','shared',() => import('./views/SharedView.vue'),'Flashcard',{props:true,meta:{back:() => '/home'}}),
  page('/shared/:token([A-Za-z0-9_-]{32,64})/study','shared-study',() => import('./views/SharedStudyView.vue'),'Flashcard',{props:true,meta:{studyFocus:true}}),
  page('/study/:sessionId','study',() => import('./views/StudyView.vue'),'Flashcard',{props:true,meta:{nav:'decks',studyFocus:true}}),
  page('/summary/:sessionId','summary',() => import('./views/StudySummary.vue'),'Flashcard',{props:true,meta:{nav:'decks'}}),
  page('/multiple-choice/:sessionId([a-fA-F0-9-]{36})','multiple-choice',() => import('./views/MultipleChoiceView.vue'),'Flashcard',{props:true,meta:{nav:'decks',studyFocus:true}}),
  page('/gwa-calculator','gwa',() => import('./views/GwaView.vue'),'GWA Calculator'),
  {path:'/notes',redirect:'/gwa-calculator'},
  page('/rooms/:code','room',() => import('./views/RoomEntry.vue'),'Study Room',{props:true,meta:{studyFocus:true}}),
  page('/class-schedule','class-schedule',() => import('./views/ScheduleView.vue'),'Class Schedule'),
  page('/pomodoro','pomodoro',() => import('./views/PomodoroView.vue'),'Pomodoro'),
  page('/search','search',() => import('./views/SearchView.vue'),'Search'),
  page('/profile','profile',profile,'Profile'),
  page('/u/:username','public-profile',profile,'Profile',{props:true,meta:{guest:true}}),
  page('/people','people',() => import('./views/PeopleView.vue'),'Find profiles',{meta:{guest:true}}),
  {path:'/settings', redirect:'/profile'},
  page('/help','help',accountPage,'Help'),
  page('/friend/:username([A-Za-z0-9_]{3,32})','friend',profile,'Profile',{props:true,meta:{back:() => '/home'}}),
  page('/:pathMatch(.*)*','missing',() => import('./views/NotFound.vue'),'Page not found'),
]});
const authentication = initAuthentication(router);
setRouter(router);
// Same-origin links route inside the SPA instead of reloading the page.
document.addEventListener('click', event => {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest?.('a[href]');
  if (!link || (link.target && link.target !== '_self') || link.hasAttribute('download')) return;
  const path = internalLinkPath(link.getAttribute('href'), location.href);
  if (!path) return;
  event.preventDefault();
  void router.push(path);
});
router.beforeEach(to => {
  if (to.meta.guest) return true;
  const publicPage = ['login','signup'].includes(to.name);
  if (!account.value && !publicPage) return ['shared','shared-study'].includes(to.name)
    ? {name:'login',query:{returnTo:'/shared/' + to.params.token}} : '/login';
  if (account.value && publicPage) return '/home';
});

try { await authentication.restore(); }
catch (failure) { loginMessage.value = failure.message; }

const app = createApp(App);
app.provide('auth',authentication);
app.config.errorHandler = error => showNotice(error.message || 'Something went wrong. Please try again.');
app.use(router);
await router.isReady();
app.mount('#queezo-root');
if (import.meta.hot) import.meta.hot.dispose(() => { app.unmount(); authentication.stop(); });
