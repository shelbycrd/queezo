<script setup>
import {computed, inject, onMounted, reactive, ref, watch} from 'vue';
import {passwordStrength} from '../../js/password-strength.js';
import {loginMessage} from '../services/session.js';
import {showNotice} from '../services/notice.js';
import {useLifetime} from '../composables/lifecycle.js';
import PasswordField from '../components/PasswordField.vue';

const props = defineProps({signup:Boolean});
const auth = inject('auth');
const {active} = useLifetime();
const form = reactive({display_name:'', username:'', email:'', password:'', confirm_password:''});
const pending = ref(false), confirmation = ref();
const strength = computed(() => passwordStrength(form.password, [form.display_name, form.username, form.email]));
watch(() => [form.password, form.confirm_password], () => {
  confirmation.value?.validate(form.confirm_password && form.confirm_password !== form.password ? 'Passwords do not match.' : '');
});
onMounted(() => {
  if (!props.signup && loginMessage.value) {
    showNotice(loginMessage.value);
    loginMessage.value = '';
  }
});
async function submit() {
  if (pending.value) return;
  pending.value = true;
  try {
    await auth.authenticate(props.signup ? 'signup' : 'login', props.signup ? {...form} : {email:form.email,password:form.password}, active);
  } catch (error) {
    if (active()) showNotice(error.message);
  } finally {
    form.password = ''; form.confirm_password = ''; pending.value = false;
  }
}
</script>
<template>
  <section v-if="!signup" class="panel login-panel">
    <p class="eyebrow">Welcome to Queezo</p><h1>Log in to Queezo.</h1><p class="muted">New here? <a href="#/signup">Create an account</a>.</p>
    <form id="login-form" @submit.prevent="submit"><label for="login-email">Email</label><input id="login-email" v-model="form.email" name="email" type="email" autocomplete="username" maxlength="254" required>
      <label for="login-password">Password</label><PasswordField id="login-password" v-model="form.password" label="Password" name="password" autocomplete="current-password" required />
      <p id="login-message" class="hint" role="status"></p><button type="submit" :disabled="pending">{{ pending ? 'Logging in…' : 'Log in' }}</button>
    </form>
  </section>
  <section v-else class="panel signup-panel">
    <h1>Create your account</h1><p class="muted">Already have an account? <a href="#/login">Log in</a>.</p>
    <form id="signup-form" @submit.prevent="submit"><div class="signup-fields">
      <div><label for="signup-name">Display name</label><input id="signup-name" v-model="form.display_name" name="display_name" autocomplete="nickname" maxlength="80" required></div>
      <div><label for="signup-username">Username</label><input id="signup-username" v-model="form.username" name="username" autocomplete="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9_]{3,32}" required><p class="hint">3–32 letters, numbers, or underscores. Must be unique.</p></div>
      <div class="full-width"><label for="signup-email">Email</label><input id="signup-email" v-model="form.email" name="email" type="email" autocomplete="email" maxlength="254" required></div>
      <div class="full-width"><label for="signup-password">Password</label><PasswordField id="signup-password" v-model="form.password" label="Password" name="password" autocomplete="new-password" minlength="11" maxlength="1024" required aria-describedby="strength-label password-advice" />
        <div class="strength-heading"><span id="strength-label">Estimated strength</span><strong id="strength-level">{{ strength.level }}</strong></div>
        <progress id="password-strength" max="100" :value="strength.score" aria-label="Estimated password strength" :aria-valuetext="strength.level" :data-level="strength.level.toLowerCase()"></progress>
        <ul id="password-advice" class="hint"><li v-for="tip in strength.tips" :key="tip">{{ tip }}</li></ul><p class="hint">Only the 11-character minimum is required. Strength advice is optional.</p>
      </div>
      <div class="full-width"><label for="signup-confirm">Confirm password</label><PasswordField id="signup-confirm" ref="confirmation" v-model="form.confirm_password" label="Confirm password" name="confirm_password" autocomplete="new-password" minlength="11" maxlength="1024" required /></div>
    </div><button type="submit" :disabled="pending">{{ pending ? 'Creating account…' : 'Sign up' }}</button></form>
  </section>
</template>
