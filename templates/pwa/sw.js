{% load static %}/* Service worker — سامانه انبارداری.
 * صفحه‌های پویا (موجودی، فاکتور، گزارش) هرگز کش نمی‌شوند تا داده‌ی انبار همیشه زنده باشد.
 * فقط فایل‌های ثابت (/static/) و صفحه‌ی آفلاین کش می‌شوند.
 */
const VERSION = "fibonacci-v1";
const STATIC_CACHE = VERSION + "-static";
const OFFLINE_URL = "{% url 'pwa_offline' %}";
const STATIC_PREFIX = "{% get_static_prefix %}";
const PRECACHE = [
  OFFLINE_URL,
  "{% static 'icons/icon-192.png' %}",
  "{% static 'icons/icon-512.png' %}"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.indexOf("fibonacci-") === 0 && key.indexOf(VERSION) !== 0)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // صفحه‌ها: همیشه از شبکه؛ فقط اگر اینترنت قطع بود صفحه‌ی آفلاین
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // فایل‌های ثابت: اول کش، همزمان به‌روزرسانی از شبکه
  if (url.pathname.indexOf(STATIC_PREFIX) === 0) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          const network = fetch(request)
            .then((response) => {
              if (response && response.ok) cache.put(request, response.clone());
              return response;
            })
            .catch(() => cached);
          return cached || network;
        })
      )
    );
  }
  // بقیه (APIها، media، ...) دست‌نخورده از شبکه می‌روند
});
