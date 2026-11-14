// Session and CSRF information stays in memory. The session cookie is HttpOnly.
let user = null;
let version = 0;
let unauthorized = () => {};

export const authenticatedUser = () => user;
export const authVersion = () => version;
export const csrfToken = () => user?.csrf_token || '';
export function setAuthenticatedUser(value) {
  if (user?.id !== value?.id || user?.csrf_token !== value?.csrf_token) version++;
  user = value ? {id:value.id, email:value.email, csrf_token:value.csrf_token} : null;
}
export function onUnauthorized(handler) { unauthorized = handler; }
export function handleUnauthorized() { unauthorized(); }
