// Lets the web app be added to a home screen. It caches nothing: the app always comes fresh from your computer,
// so an update to Hallucinate is never hidden behind an old copy, and nothing of your library is kept here.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
