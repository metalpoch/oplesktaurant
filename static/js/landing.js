/* Oplesktaurant: paisaje decorativo independiente del catálogo de lectura. */
(function () {
  "use strict";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function renderList(locations) {
    var list = document.getElementById("locations-list");
    if (!list) return;
    list.innerHTML = "";
    locations.forEach(function (loc, index) {
      var li = el("li", "location-item");
      li.style.setProperty("--entry-delay", Math.min(index, 7) * .07 + "s");
      li.appendChild(el("span", "location-number", "DESTINO FICTICIO / " + String(index + 1).padStart(2, "0")));
      li.appendChild(el("h3", null, loc.name));
      var details = el("details");
      details.appendChild(el("summary", "", "Detalles del destino"));
      details.appendChild(el("p", "address", loc.address));
      li.appendChild(details);
      list.appendChild(li);
    });
  }

  function loadLocations() {
    fetch("/api/locations", { headers: { "Accept": "application/json" } })
      .then(function (res) {
        return res.json().catch(function () { return []; }).then(function (data) {
          if (!res.ok) throw new Error((data && data.error) || ("Error HTTP " + res.status));
          return data;
        });
      })
      .then(function (locations) {
        renderList(locations);
        var count = document.getElementById("catalog-count");
        if (count) {
          count.textContent = locations.length === 1
            ? "1 espacio en el catálogo"
            : locations.length + " espacios en el catálogo";
        }
        var empty = document.getElementById("locations-empty");
        if (empty) empty.hidden = locations.length !== 0;
      })
      .catch(function () {
        var count = document.getElementById("catalog-count");
        if (count) {
           count.textContent = "Los destinos no están disponibles ahora.";
        }
        var empty = document.getElementById("locations-empty");
        if (empty) {
          empty.hidden = false;
          empty.textContent = "La consulta falló. Vuelve a cargar la página para intentarlo de nuevo.";
        }
      });
  }

  function init() {
    buildLandscape();
    initAmbient();
    var heroBtn = document.getElementById("hero-chat-open");
    if (heroBtn) {
      heroBtn.addEventListener("click", function () {
        if (window.OpleChat) window.OpleChat.open();
      });
    }
    loadLocations();
  }

  function buildLandscape() {
    var ground = document.getElementById("urban-buildings");
    if (!ground) return;
    ground.replaceChildren();
    // 70 volúmenes decorativos; nunca son registros del catálogo.
    for (var row = 0; row < 7; row++) {
      for (var col = 0; col < 10; col++) {
        var index = row * 10 + col;
        var landmark = index % 13 === 4;
        var building = el("div", "cuboid urban-block" + (landmark ? " urban-pavilion" : ""));
        building.style.left = (120 + col * 230) + "px";
        building.style.top = (120 + row * 230) + "px";
        building.style.setProperty("--w", (landmark ? 124 : 72 + index % 4 * 16) + "px");
        building.style.setProperty("--h", (landmark ? 62 : 85 + index * 17 % 150) + "px");
        building.style.setProperty("--glow-delay", -(index % 11) + "s");
        ["roof", "front", "back", "left", "right"].forEach(function (face) { building.appendChild(el("span", "face " + face)); });
        ground.appendChild(building);
      }
    }
  }

  function initAmbient() {
    var button = document.getElementById("ambient-toggle");
    if (!button) return;
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    var manualPause = false;
    function sync() {
      var paused = manualPause || reduced.matches;
      document.body.classList.toggle("ambient-paused", paused);
      button.setAttribute("aria-pressed", String(paused));
      button.disabled = reduced.matches;
      button.textContent = reduced.matches ? "Ambiente en reposo · movimiento reducido" : paused ? "Reanudar ambiente" : "Pausar ambiente";
    }
    button.addEventListener("click", function () { manualPause = !manualPause; sync(); });
    if (reduced.addEventListener) reduced.addEventListener("change", sync);
    else if (reduced.addListener) reduced.addListener(sync);
    function visibility() { document.body.classList.toggle("page-hidden", document.hidden); }
    document.addEventListener("visibilitychange", visibility);
    sync(); visibility();
    var landscape = document.getElementById("mapa");
    if (landscape && typeof IntersectionObserver !== "undefined") {
      // En reposo hasta conocer su visibilidad; no modifica pausa manual ni aria.
      landscape.classList.toggle("ambient-offscreen", true);
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          entry.target.classList.toggle("ambient-offscreen", !entry.isIntersecting);
        });
      }, { threshold: 0 });
      observer.observe(landscape);
    }
    document.body.classList.toggle("ambient-ready", true);
    button.hidden = false;
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

})();
