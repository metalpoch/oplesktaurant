/* Oplesktaurant - login del personal (sin auto-registro). */
(function () {
  "use strict";

  function getCsrfToken() {
    return fetch("/api/session", { headers: { "Accept": "application/json" } })
      .then(function (res) { return res.json().catch(function () { return {}; }); })
      .then(function (data) { return (data && data.csrf_token) || ""; })
      .catch(function () { return ""; });
  }

  var DEFAULT_NEXT = "/admin";

  /* Decide a qué ruta local redirigir tras el login (evita open redirect).
   * Solo acepta rutas del mismo origen: descarta "//host" y "\host"
   * (protocol-relative o normalizados por el navegador), orígenes externos y
   * candidatos que no sean rutas locales. En cualquier otro caso, "/admin". */
  function safeNextPath(candidate, origin) {
    if (typeof candidate !== "string" || candidate.charAt(0) !== "/") {
      return DEFAULT_NEXT;
    }
    // Barras invertidas: algunos navegadores las tratan como "/".
    if (candidate.indexOf("\\") !== -1) return DEFAULT_NEXT;
    // Rutas protocol-relative ("//host").
    if (candidate.charAt(1) === "/") return DEFAULT_NEXT;

    var base = origin || (typeof window !== "undefined" ? window.location.origin : "");
    if (!base) return DEFAULT_NEXT;
    var resolved;
    try {
      resolved = new URL(candidate, base);
    } catch (err) {
      return DEFAULT_NEXT;
    }
    if (resolved.origin !== base) return DEFAULT_NEXT;
    return resolved.pathname + resolved.search + resolved.hash;
  }

  function init() {
    var form = document.getElementById("login-form");
    if (!form) return;
    var email = document.getElementById("login-email");
    var password = document.getElementById("login-password");
    var errorEl = document.getElementById("login-error");
    var submit = document.getElementById("login-submit");
    var csrf = "";

    getCsrfToken().then(function (token) { csrf = token; });

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      if (errorEl) errorEl.textContent = "";
      if (!email || !password) return;
      var body = { email: email.value.trim(), password: password.value };
      if (submit) submit.disabled = true;

      fetch("/api/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-CSRF-Token": csrf
        },
        body: JSON.stringify(body)
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            throw new Error((data && data.error) || ("Error HTTP " + res.status));
          }
          return data;
        });
      }).then(function () {
        var params = new URLSearchParams(window.location.search);
        window.location.assign(safeNextPath(params.get("next")));
      }).catch(function (err) {
        if (errorEl) errorEl.textContent = err.message || "No se pudo iniciar sesión.";
        if (submit) submit.disabled = false;
      });
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  // Exporta la función pura para pruebas en Node (no afecta al navegador).
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { safeNextPath: safeNextPath };
  }
})();
