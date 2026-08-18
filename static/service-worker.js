// service-worker.js
// Deliberately minimal: Local Share's whole point is showing live, current
// files, so we do NOT cache uploads/pages for offline use - that would
// show stale file lists. This just satisfies Chrome's PWA installability
// requirement (a registered service worker with a fetch handler) so
// "Add to Home Screen" gives a real standalone app window instead of a
// plain browser-tab shortcut.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
