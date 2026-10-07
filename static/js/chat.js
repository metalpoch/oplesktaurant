/* Oplestaurants - widget de chat compartido.
 *
 * La identidad se decide en el servidor según la sesión: Mesi (público) o
 * Nbapeh (panel autenticado). El navegador nunca conoce la clave del proveedor
 * ni habla directamente con el servicio de IA.
 */
(function () {
  "use strict";

  var IDENTITIES = {
    mesi: {
      name: "Mesi",
      subtitle: "Asistente de Oplestaurants",
      title: "Mesi",
      input: "Escribe un mensaje",
      placeholder: "Escríbeme y te cuento sobre Oplestaurants."
    },
    nbapeh: {
      name: "Nbapeh",
      subtitle: "Ayudante de la plataforma",
      title: "Nbapeh",
      input: "Pregúntame sobre el panel",
      placeholder: "Pregúntame cómo usar el panel."
    }
  };

  var MAX_HISTORY = 8;

  function toast(message, isError) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    el.classList.toggle("error", !!isError);
    window.clearTimeout(el._timer);
    el._timer = window.setTimeout(function () { el.hidden = true; }, 3500);
  }

  function fetchSession() {
    return fetch("/api/session", { headers: { "Accept": "application/json" } })
      .then(function (res) { return res.json().catch(function () { return {}; }); })
      .then(function (data) { return data || {}; })
      .catch(function () { return {}; });
  }

  function init() {
    var toggle = document.getElementById("chat-toggle");
    var panel = document.getElementById("chat-panel");
    var closeBtn = document.getElementById("chat-close");
    var form = document.getElementById("chat-form");
    var input = document.getElementById("chat-input");
    var send = document.getElementById("chat-send");
    var statusEl = document.getElementById("chat-status");
    var messages = document.getElementById("chat-messages");
    var titleEl = document.getElementById("chat-title");
    var subtitleEl = document.getElementById("chat-subtitle");
    var labelEl = document.getElementById("chat-toggle-label");
    if (!toggle || !panel || !closeBtn || !messages) return;

    var history = [];
    var busy = false;
    var identityKey = "mesi";

    function applyIdentity(key) {
      identityKey = IDENTITIES[key] ? key : "mesi";
      var cfg = IDENTITIES[identityKey];
      if (titleEl) titleEl.textContent = cfg.title;
      if (subtitleEl) subtitleEl.textContent = cfg.subtitle;
      if (labelEl) labelEl.textContent = cfg.name;
      if (input) input.setAttribute("placeholder", cfg.input);
      if (toggle) toggle.setAttribute("aria-label", "Abrir asistente " + cfg.name);
      if (input) input.setAttribute("aria-label", "Mensaje para " + cfg.name);
    }

    function openPanel() {
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Cerrar asistente");
      if (input) input.focus();
    }

    function closePanel(returnFocus) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Abrir asistente " + IDENTITIES[identityKey].name);
      if (returnFocus) toggle.focus();
    }

    function appendBubble(role, text) {
      var placeholder = messages.querySelector(".chat-placeholder");
      if (placeholder) placeholder.remove();
      var bubble = document.createElement("div");
      bubble.className = "chat-message " + role;
      bubble.textContent = text;
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
    }

    function setBusy(value) {
      busy = value;
      if (input) input.disabled = value;
      if (send) send.disabled = value;
    }

    toggle.addEventListener("click", function () {
      if (panel.hidden) { openPanel(); } else { closePanel(true); }
    });
    closeBtn.addEventListener("click", function () { closePanel(true); });

    document.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape" && !panel.hidden) closePanel(true);
    });

    if (form) {
      form.addEventListener("submit", function (evt) {
        evt.preventDefault();
        if (busy || !input) return;
        var text = input.value.trim();
        if (!text) return;
        appendBubble("user", text);
        history.push({ role: "user", content: text });
        if (history.length > MAX_HISTORY) history = history.slice(-MAX_HISTORY);
        input.value = "";
        setBusy(true);
        if (statusEl) statusEl.textContent = "Escribiendo…";

        fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ message: text, history: history.slice(0, -1) })
        }).then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            if (!res.ok) {
              throw new Error((data && data.error) || ("Error HTTP " + res.status));
            }
            return data;
          });
        }).then(function (data) {
          if (data.identity) applyIdentity(data.identity);
          var reply = data.reply || "…";
          appendBubble("assistant", reply);
          history.push({ role: "assistant", content: reply });
          if (history.length > MAX_HISTORY) history = history.slice(-MAX_HISTORY);
          if (statusEl) statusEl.textContent = "";
        }).catch(function (err) {
          if (statusEl) statusEl.textContent = "";
          toast(err.message || "No se pudo enviar el mensaje.", true);
        }).then(function () {
          setBusy(false);
        });
      });
    }

    fetchSession().then(function (data) {
      applyIdentity(data && data.authenticated ? "nbapeh" : "mesi");
    });

    window.OpleChat = { open: openPanel, close: closePanel };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
