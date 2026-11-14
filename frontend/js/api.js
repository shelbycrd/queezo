import {authVersion, csrfToken, handleUnauthorized} from './auth-state.js';

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, {method = 'GET', body, ignoreUnauthorized = false} = {}) {
  method = method.toUpperCase();
  const version = authVersion();
  const headers = body === undefined ? {} : {'Content-Type': 'application/json'};
  if (!['GET','HEAD','OPTIONS'].includes(method) && csrfToken()) headers['X-CSRF-Token'] = csrfToken();
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method, cache: 'no-store', credentials:'same-origin', headers,
      ...(body === undefined ? {} : {body: JSON.stringify(body)}),
    });
  } catch {
    throw new ApiError('Cannot reach Queezo. Check that the containers are running.', 0);
  }
  if (!path.startsWith('/auth/') && version !== authVersion()) {
    throw new ApiError('Your account session changed. Open this page again.', 409);
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!path.startsWith('/auth/') && version !== authVersion()) {
    throw new ApiError('Your account session changed. Open this page again.', 409);
  }
  if (!response.ok) {
    if (response.status === 401 && !ignoreUnauthorized) handleUnauthorized();
    const details = data?.error?.details?.map(e => `${e.field}: ${e.message}`).join(' ');
    throw new ApiError(details || data?.error?.message || `Request failed (${response.status}).`, response.status);
  }
  return data;
}
