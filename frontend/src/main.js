import {createApp} from 'vue';
import {createRouter, createWebHashHistory, createWebHistory} from 'vue-router';
import App from './App.vue';
import {account, initAuthentication, loginMessage} from './services/session.js';
import {showNotice} from './services/notice.js';
import '../css/styles.css';
import '../css/pomodoro.css';
import '../css/auth.css';
import '../css/theme.css';
import '../css/cloud-theme.css';
import '../css/multiple-choice.css';
import '../css/profiles.css';

const cleanProfileEntry = /^\/u(?:\/|$)/.test(location.pathname);
if (!cleanProfileEntry && /^#[^/]/.test(location.hash)) history.replaceState(history.state, '', '#/' + location.hash.slice(1));

const page = (path, name, component, title, options = {}) => ({path, name, component, ...options, meta:{title,...options.meta}});
const deck = () => import('./views/DeckView.vue');
const auth = () => import('./views/AuthView.vue');
const accountPage = () => import('./views/AccountView.vue');
const profile = () => import('./views/ProfileView.vue');
const router = createRouter({history:cleanProfileEntry ? createWebHistory() : createWebHashHistory(), routes:[
  {path:'/', redirect:'/dashboard'},
  page('/login','login',auth,'Log in'),
  page('/signup','signup',auth,'Sign up',{props:{signup:true}}),
  page('/dashboard','dashboard',() => import('./views/DashboardView.vue'),'Home'),
  page('/decks/:create(new)?','decks',() => import('./views/DecksView.vue'),'Flashcard',{props:true}),
  page('/deck/:deckId(\\d+)/:action(add)?','deck',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => r.params.action ? '#/deck/' + r.params.deckId : '#/decks'}}),
  page('/deck/:deckId(\\d+)/edit/:cardId(\\d+)','edit',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => '#/deck/' + r.params.deckId}}),
  page('/deck/:deckId(\\d+)/page/:pageNumber(\\d+)','deck-page',deck,'Flashcard',{props:true,meta:{nav:'decks',back:r => '#/deck/' + r.params.deckId}}),
  page('/shared/:token([A-Za-z0-9_-]{32,64})','shared',() => import('./views/SharedView.vue'),'Flashcard',{props:true,meta:{back:() => '#/dashboard'}}),
  page('/shared/:token([A-Za-z0-9_-]{32,64})/study','shared-study',() => import('./views/SharedStudyView.vue'),'Flashcard',{props:true,meta:{studyFocus:true}}),
  page('/study/:sessionId','study',() => import('./views/StudyView.vue'),'Flashcard',{props:true,meta:{nav:'decks',studyFocus:true}}),
  page('/summary/:sessionId','summary',() => import('./views/StudySummary.vue'),'Flashcard',{props:true,meta:{nav:'decks'}}),
  page('/multiple-choice/:sessionId([a-fA-F0-9-]{36})','multiple-choice',() => import('./views/MultipleChoiceView.vue'),'Flashcard',{props:true,meta:{nav:'decks',studyFocus:true}}),
  page('/gwa','gwa',() => import('./views/GwaView.vue'),'GWA Calculator'),
  {path:'/notes',redirect:'/gwa'},
  page('/pomodoro','pomodoro',() => import('./views/PomodoroView.vue'),'Pomodoro'),
  page('/profile','profile',profile,'Profile'),
  page('/u/:username','public-profile',profile,'Profile',{props:true,meta:{guest:true}}),
  page('/people','people',() => import('./views/PeopleView.vue'),'Find profiles',{meta:{guest:true}}),
  page('/settings','settings',accountPage,'Settings',{props:{section:'settings'}}),
  page('/help','help',accountPage,'Help',{props:{section:'help'}}),
  page('/friend/:username([A-Za-z0-9_]{3,32})','friend',profile,'Profile',{props:true,meta:{back:() => '#/dashboard'}}),
  page('/:pathMatch(.*)*','missing',() => import('./views/NotFound.vue'),'Page not found',{meta:{guest:cleanProfileEntry}}),
]});
const authentication = initAuthentication(router);
router.beforeEach(to => {
  // Clean profile URLs share the same App shell. Other pages retain their hash URLs.
  if (cleanProfileEntry && !['public-profile','missing'].includes(to.name)) {
    location.replace('/#' + to.fullPath);
    return false;
  }
  if (to.meta.guest) return true;
  const publicPage = ['login','signup'].includes(to.name);
  if (!account.value && !publicPage) return ['shared','shared-study'].includes(to.name)
    ? {name:'login',query:{returnTo:'/shared/' + to.params.token}} : '/login';
  if (account.value && publicPage) return '/dashboard';
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
