/* Maqueta interactiva del panel de Oplesktaurant. Sin bucle de animación. */
(function () {
  "use strict";
  function position(loc) {
    var x = Number(loc.pos_x), y = Number(loc.pos_y);
    if (loc.pos_x == null || loc.pos_y == null || !Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null;
    return { x: 8 + x * 84, y: 8 + y * 84 };
  }
  function fitScene(width, height, flat, geometry) {
    // Extensión definida junto al tamaño CSS: incluye borde, cubos y foco.
    // En 3D una esfera envolvente protege cualquier rotación y perspectiva.
    var availableX = Math.max(0, width / 2 - geometry.clearance);
    var availableY = Math.max(0, height / 2 - geometry.clearance);
    if (flat) return Math.max(0, Math.min(1, availableX / geometry.extent, availableY / geometry.extent));
    var radius = Math.hypot(geometry.extent, geometry.extent, geometry.maxHeight);
    var available = Math.min(availableX, availableY);
    return Math.min(1, available / (radius * (1 + available / geometry.perspective)));
  }
  function volume(className, x, y, height, label) {
    var node = document.createElement(className === "restaurant" ? "button" : "div");
    node.className = "cuboid " + className;
    node.style.left = x + "%";
    node.style.top = y + "%";
    node.dataset.x = x;
    node.dataset.y = y;
    node.style.setProperty("--h", height + "px");
    ["roof", "front", "back", "left", "right"].forEach(function (face) {
      var side = document.createElement("span");
      side.className = "face " + face;
      side.setAttribute("aria-hidden", "true");
      if (face === "roof" && label) side.textContent = label;
      node.appendChild(side);
    });
    return node;
  }
  function select(id) {
    var loc = current.find(function (item) { return String(item.id) === String(id); });
    if (!loc) return;
    selectedId = String(loc.id);
    document.querySelectorAll("[data-location-select]").forEach(function (button) {
      var selected = String(button.dataset.locationSelect) === selectedId;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.classList.remove("spotlight");
      if (selected) button.classList.toggle("spotlight", true);
    });
    document.querySelectorAll(".city-selection").forEach(function (note) {
      note.textContent = loc.name + " · " + loc.address + (loc.is_demo ? " · Datos ficticios de demostración" : "") + (!position(loc) ? " · Sin posición válida en la maqueta" : "");
    });
  }
  var current = [];
  var selectedId = null;
  function focusSceneControl(card) {
    // Solo controles visibles y habilitados, con summary como respaldo.
    var controls = Array.from(card.querySelectorAll("button, summary"));
    function available(node) {
      return !node.disabled && !node.hasAttribute("data-location-select") && node.getClientRects().length > 0;
    }
    var control = controls.find(function (node) { return node.tagName === "BUTTON" && available(node); }) ||
      controls.find(function (node) { return node.tagName === "SUMMARY" && available(node); });
    if (control) control.focus({ preventScroll: true });
  }
  function render(locations) {
    current = locations;
    document.querySelectorAll(".city-decor .cuboid").forEach(function (building) {
      building.hidden = locations.some(function (loc) {
        var p = position(loc);
        return p && Math.abs(p.x - Number(building.dataset.x)) < 9 && Math.abs(p.y - Number(building.dataset.y)) < 9;
      });
    });
    document.querySelectorAll(".city-pins").forEach(function (pins) {
      var active = document.activeElement;
      var focusedId = pins.contains(active) ? active.dataset.locationSelect : null;
      pins.replaceChildren();
      locations.forEach(function (loc, index) {
        var p = position(loc);
        if (!p) return; // No inventar una posición para datos inválidos.
        var building = volume("restaurant", p.x, p.y, 28, index + 1);
        building.type = "button";
        building.dataset.locationSelect = loc.id;
        building.setAttribute("aria-label", "Seleccionar " + loc.name + (loc.is_demo ? " · Demostración" : ""));
        building.setAttribute("aria-pressed", "false");
        building.addEventListener("click", function () { select(loc.id); });
        pins.appendChild(building);
      });
      if (focusedId) {
        var next = Array.from(pins.children).find(function (button) { return String(button.dataset.locationSelect) === String(focusedId); });
        if (next) next.focus({ preventScroll: true });
        else focusSceneControl(pins.closest(".city-card"));
      }
    });
    document.querySelectorAll(".city-selection").forEach(function (note) {
      note.textContent = locations.length ? "Selecciona un restaurante iluminado o utiliza el listado." : "Sin sucursales cargadas. Los edificios son decoración.";
    });
    if (locations.some(function (loc) { return String(loc.id) === selectedId; })) select(selectedId);
    else {
      selectedId = null;
      document.querySelectorAll("[data-location-select]").forEach(function (button) {
        button.classList.remove("selected");
        button.classList.remove("spotlight");
        button.setAttribute("aria-pressed", "false");
      });
    }
  }
  function wireCamera(card, board, resize) {
    var tilt = card.querySelector("[data-city-tilt]");
    var rotate = card.querySelector("[data-city-rotate]");
    var flatButton = card.querySelector("[data-city-flat]");
    function update() {
      board.style.setProperty("--tilt", tilt.value + "deg");
      board.style.setProperty("--rotation", rotate.value + "deg");
    }
    tilt.addEventListener("input", update);
    rotate.addEventListener("input", update);
    function resetCamera() {
      card.classList.remove("scene-flat");
      flatButton.setAttribute("aria-pressed", "false");
      tilt.disabled = false; rotate.disabled = false;
      tilt.value = 58; rotate.value = -32;
      resize();
      update();
    }
    card.querySelector("[data-city-reset]").addEventListener("click", resetCamera);
    flatButton.addEventListener("click", function (event) {
      var flat = card.classList.toggle("scene-flat");
      event.currentTarget.setAttribute("aria-pressed", String(flat));
      tilt.disabled = flat; rotate.disabled = flat;
      resize();
    });
    update();
  }
  function init() {
    if (typeof IntersectionObserver !== "undefined" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      var reveals = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.remove("reveal-pending");
            reveals.unobserve(entry.target);
          }
        });
      }, { threshold: .06 });
      document.querySelectorAll(".reveal").forEach(function (node) {
        if (node.getBoundingClientRect().top > window.innerHeight) {
          node.classList.add("reveal-pending");
          reveals.observe(node);
        }
      });
    }
    document.querySelectorAll(".city-card").forEach(function (card) {
      var board = card.querySelector(".city-board");
      var stage = card.querySelector(".map-stage");
      var styles = window.getComputedStyle(card);
      var geometry = {
        extent: Number(styles.getPropertyValue("--city-extent")),
        maxHeight: Number(styles.getPropertyValue("--city-max-height")),
        clearance: Number(styles.getPropertyValue("--city-clearance")),
        perspective: Number(styles.getPropertyValue("--city-perspective"))
      };
      var decor = card.querySelector(".city-decor");
      // Bloques puramente decorativos: no representan barrios o edificios reales.
      for (var row = 0; row < 4; row++) {
        for (var col = 0; col < 4; col++) {
          decor.appendChild(volume("building", 10 + col * 24, 12 + row * 23, 25 + ((row * 3 + col * 7) % 5) * 13));
          decor.appendChild(volume("building", 19 + col * 24, 12 + row * 23, 20 + ((row + col) % 3) * 14));
        }
      }
      function resize() {
        board.style.setProperty("--scale", fitScene(stage.clientWidth, stage.clientHeight, card.classList.contains("scene-flat"), geometry));
      }
      wireCamera(card, board, resize);
      if (typeof ResizeObserver !== "undefined") new ResizeObserver(resize).observe(stage);
      else window.addEventListener("resize", resize);
      resize();
    });
    document.addEventListener("visibilitychange", function () {
      document.body.classList.toggle("page-hidden", document.hidden);
    });
  }
  if (typeof window !== "undefined") window.OpleCity = { render: render, select: select };
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { position: position, fitScene: fitScene };
})();
