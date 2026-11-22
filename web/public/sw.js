// Service worker: recibe las notificaciones Web Push del notificador de StockEye.
self.addEventListener("push", (evento) => {
  let datos = {};
  try { datos = evento.data ? evento.data.json() : {}; } catch { datos = { cuerpo: evento.data && evento.data.text() }; }
  const titulo = datos.titulo || "StockEye";
  evento.waitUntil(self.registration.showNotification(titulo, {
    body: datos.cuerpo || "",
    icon: "/icono.svg",
    badge: "/icono.svg",
    tag: datos.numero || undefined,
    data: { url: datos.url || "/" },
  }));
});

self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  const url = new URL(evento.notification.data && evento.notification.data.url || "/", self.location.origin).href;
  evento.waitUntil((async () => {
    const ventanas = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const v of ventanas) {
      if (v.url.startsWith(self.location.origin)) { await v.focus(); return v.navigate(url); }
    }
    return clients.openWindow(url);
  })());
});
