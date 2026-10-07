/* Oplestaurants - landing: carga ubicaciones públicas y dibuja el mapa. */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  // Margen dentro del viewBox 1000x600 para colocar los pines.
  var MAP = { x0: 90, x1: 910, y0: 150, y1: 540 };
  var DEMO_BADGE_TEXT = "Datos ficticios de demostración";

  function isDemo(loc) {
    return !!(loc && loc.is_demo);
  }

  function hasDemo(locations) {
    return (locations || []).some(isDemo);
  }

  function demoBadgeLabel(loc) {
    return isDemo(loc) ? DEMO_BADGE_TEXT : null;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  function project(loc, index) {
    var nx = Number(loc.pos_x);
    var ny = Number(loc.pos_y);
    if (!isFinite(nx) || nx < 0 || nx > 1) nx = (index % 3) / 2;
    if (!isFinite(ny) || ny < 0 || ny > 1) ny = 0.5;
    return {
      x: MAP.x0 + nx * (MAP.x1 - MAP.x0),
      y: MAP.y0 + ny * (MAP.y1 - MAP.y0)
    };
  }

  function drawPin(loc, index) {
    var p = project(loc, index);
    var g = svgEl("g", {
      "class": "map-pin",
      tabindex: "0",
      role: "img",
      "aria-label": loc.name + ". " + loc.address +
        (loc.is_demo ? ". Datos ficticios de demostración." : ".")
    });

    g.appendChild(svgEl("line", {
      x1: p.x, y1: p.y, x2: p.x, y2: p.y - 26,
      stroke: "#7c3aed", "stroke-width": 3, "stroke-linecap": "round"
    }));
    g.appendChild(svgEl("circle", {
      cx: p.x, cy: p.y - 30, r: 11, fill: "#ede9fe",
      stroke: "#7c3aed", "stroke-width": 3
    }));
    g.appendChild(svgEl("circle", {
      "class": "dot", cx: p.x, cy: p.y - 30, r: 5, fill: "#7c3aed"
    }));

    var title = svgEl("title", {});
    title.textContent = loc.name + " — " + loc.address;
    g.appendChild(title);

    var label = svgEl("text", {
      x: p.x + 14, y: p.y - 26, "font-size": "15",
      "font-family": "system-ui, sans-serif", "font-weight": "700", fill: "#312e81"
    });
    label.textContent = String(index + 1);
    g.appendChild(label);

    return g;
  }

  function renderList(locations) {
    var list = document.getElementById("locations-list");
    if (!list) return;
    list.innerHTML = "";
    locations.forEach(function (loc) {
      var li = el("li", "location-item");
      li.appendChild(el("h3", null, loc.name));
      li.appendChild(el("p", "address", loc.address));
      var badge = demoBadgeLabel(loc);
      if (badge) {
        li.appendChild(el("span", "badge demo", badge));
      }
      list.appendChild(li);
    });
    applyDemoIndicators(locations);
  }

  /* Muestra la leyenda/nota de datos ficticios solo si hay filas demo. */
  function applyDemoIndicators(locations) {
    var show = hasDemo(locations);
    var legend = document.getElementById("map-demo-legend");
    if (legend) legend.hidden = !show;
    var note = document.getElementById("map-demo-note");
    if (note) note.hidden = !show;
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
        var pins = document.getElementById("map-pins");
        if (pins) {
          pins.innerHTML = "";
          locations.forEach(function (loc, i) { pins.appendChild(drawPin(loc, i)); });
        }
        renderList(locations);
        var count = document.getElementById("map-count");
        if (count) {
          count.textContent = locations.length === 1
            ? "1 ubicación"
            : locations.length + " ubicaciones";
        }
        var empty = document.getElementById("locations-empty");
        if (empty) empty.hidden = locations.length !== 0;
      })
      .catch(function () {
        var count = document.getElementById("map-count");
        if (count) {
          count.textContent = "No se pudieron cargar las ubicaciones.";
        }
        var empty = document.getElementById("locations-empty");
        if (empty) empty.hidden = false;
        applyDemoIndicators([]);
      });
  }

  function init() {
    var heroBtn = document.getElementById("hero-chat-open");
    if (heroBtn) {
      heroBtn.addEventListener("click", function () {
        if (window.OpleChat) window.OpleChat.open();
      });
    }
    loadLocations();
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  // Exporta helpers puros para pruebas en Node (no afecta al navegador).
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      isDemo: isDemo,
      hasDemo: hasDemo,
      demoBadgeLabel: demoBadgeLabel
    };
  }
})();
