/* Oplesktaurant - widget de chat compartido.
 *
 * Contexto fijo de página: Mr. Mesi sin S (público incluso con sesión) o
 * Nbapeh (panel autenticado). El navegador nunca conoce la clave del proveedor
 * ni habla directamente con el servicio de IA.
 */
(function () {
  "use strict";

  var IDENTITIES = {
    mesi: {
      name: "Mr. Mesi sin S",
      subtitle: "Asistente de Oplesktaurant",
      title: "Mr. Mesi sin S",
      input: "Escribe un mensaje",
      placeholder: "Escríbeme y te cuento sobre Oplesktaurant."
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
    var widget = panel.closest("[data-chat-context]");
    var context = widget && widget.getAttribute("data-chat-context");
    if (context !== "public" && context !== "admin") return;
    var identityKey = context === "admin" ? "nbapeh" : "mesi";
    var expired = false;

    function applyIdentity() {
      var cfg = IDENTITIES[identityKey];
      if (titleEl) titleEl.textContent = cfg.title;
      if (subtitleEl) subtitleEl.textContent = cfg.subtitle;
      if (labelEl) labelEl.textContent = cfg.name;
      if (input) input.setAttribute("placeholder", cfg.input);
      if (toggle) toggle.setAttribute("aria-label", (panel.hidden ? "Abrir asistente " : "Cerrar asistente ") + cfg.name);
      if (input) input.setAttribute("aria-label", "Mensaje para " + cfg.name);
      var placeholder = messages.querySelector(".chat-placeholder");
      if (placeholder) placeholder.textContent = cfg.placeholder;
    }

    function openPanel() {
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Cerrar asistente " + IDENTITIES[identityKey].name);
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
      if (input) input.disabled = value || expired;
      if (send) send.disabled = value || expired;
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
        if (busy || expired || !input) return;
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
          body: JSON.stringify({ context: context, message: text, history: history.slice(0, -1) })
        }).then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            if (!res.ok) {
              if (res.status === 401 && context === "admin") {
                expired = true;
                throw new Error("La sesión del panel ha expirado. Inicia sesión de nuevo para hablar con Nbapeh.");
              }
              throw new Error((data && data.error) || ("Error HTTP " + res.status));
            }
            return data;
          });
        }).then(function (data) {
          if (data.identity && data.identity !== identityKey) throw new Error("La respuesta no corresponde a este asistente. Inténtalo de nuevo.");
          var reply = data.reply || "…";
          appendBubble("assistant", reply);
          history.push({ role: "assistant", content: reply });
          if (history.length > MAX_HISTORY) history = history.slice(-MAX_HISTORY);
          if (statusEl) statusEl.textContent = "";
        }).catch(function (err) {
          if (statusEl) statusEl.textContent = err.message || "No se pudo enviar el mensaje.";
          toast(err.message || "No se pudo enviar el mensaje.", true);
        }).then(function () {
          setBusy(false);
        });
      });
    }

    applyIdentity();

    window.OpleChat = { open: openPanel, close: closePanel };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
