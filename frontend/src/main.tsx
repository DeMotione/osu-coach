import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";

import { App } from "./app/App";
import { isDesktop } from "./lib/desktop";

if (isDesktop) {
  // the desktop app always loads from its own server: a cached shell would only keep showing an older version of it
  void navigator.serviceWorker?.getRegistrations().then((rs) => rs.forEach((r) => void r.unregister()));
  void caches?.keys().then((ks) => ks.forEach((k) => void caches.delete(k)));
} else {
  // installable, and the app shell opens without the network; a new version replaces the old one on the next load
  registerSW({ immediate: true });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
