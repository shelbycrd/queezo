// Clean-URL helpers shared by the router setup, components, and plain services.
let activeRouter = null;

export function setRouter(router) {
  activeRouter = router;
}

// Navigate inside the SPA without a full page load (falls back before the router exists).
export function navigate(path) {
  if (activeRouter) return activeRouter.push(path);
  location.assign(path);
}

// Paths served by Nginx or the APIs rather than the Vue app.
const serverPaths = /^\/(?:api|gwa|docs|redoc|openapi\.json|assets)(?:\/|$)/;

// Old bookmarks used `/#/page` (and share links `/#shared/token`); return the clean path or null.
export function legacyHashPath(pathname, hash) {
  if ((pathname !== '/' && pathname !== '/index.html') || !/^#\/?[^/]/.test(hash)) return null;
  return '/' + hash.replace(/^#\/?/, '');
}

// For a clicked link, return the in-app path to route to, or null to let the browser handle it.
export function internalLinkPath(href, base) {
  let url;
  try { url = new URL(href, base); } catch { return null; }
  const current = new URL(base);
  if (url.origin !== current.origin) return null;
  const legacy = legacyHashPath(url.pathname, url.hash);
  if (legacy) return legacy;
  if (serverPaths.test(url.pathname)) return null;
  // Same-page fragment links keep native behavior.
  if (url.hash && url.pathname === current.pathname && url.search === current.search) return null;
  return url.pathname + url.search + url.hash;
}
