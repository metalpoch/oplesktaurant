/* Regresiones ejecutables con node:test, sin navegador ni paquetes externos. */
"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.join(__dirname, "..");
const city = require(path.join(root, "static/js/city.js"));
const cityCss = fs.readFileSync(path.join(root, "static/css/city.css"), "utf8");
const geometry = Object.fromEntries(["extent", "max-height", "clearance", "perspective"].map(key => [
  key === "max-height" ? "maxHeight" : key,
  Number(cityCss.match(new RegExp("--city-" + key + ":\\s*([0-9]+)"))[1])
]));
const boardSize = Number(cityCss.match(/--city-size:\s*([0-9]+)/)[1]);

// Solo las primitivas DOM usadas por los callbacks; no simula layout CSS.
class Node {
  constructor(tag = "div") {
    this.tag = tag;
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attrs = {};
    this.events = {};
    this.value = "";
    this.textContent = "";
    this.classes = new Set();
    this.style = { setProperty: (key, value) => { this.style[key] = String(value); } };
    this.classList = {
      contains: key => this.classes.has(key),
      remove: key => this.classes.delete(key),
      toggle: (key, force) => {
        const on = force === undefined ? !this.classes.has(key) : force;
        if (on) this.classes.add(key); else this.classes.delete(key);
        return on;
      }
    };
  }
  appendChild(child) {
    if (child.parent) child.parent.children = child.parent.children.filter(node => node !== child);
    child.parent = this; this.children.push(child); return child;
  }
  replaceChildren() { this.children.forEach(child => { child.parent = null; }); this.children = []; }
  set innerHTML(value) { assert.equal(value, ""); this.replaceChildren(); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  getAttribute(key) { return this.attrs[key] ?? null; }
  hasAttribute(key) { return key in this.attrs; }
  addEventListener(event, callback) { this.events[event] = callback; }
  click() { return this.events.click({ currentTarget: this }); }
  focus(options) {
    let root = this;
    while (root.parent) root = root.parent;
    const document = this.ownerDocument || root.ownerDocument;
    if (document && !this.disabled && this.getClientRects().length) {
      document.activeElement = this;
      this.focusOptions = options;
    }
  }
  getClientRects() {
    let child = this;
    for (let node = this; node; node = node.parent) {
      if (node.hidden || (node.tag === "details" && !node.open && node !== this && child !== node.children.find(n => n.tag === "summary"))) return [];
      child = node;
    }
    return [{}];
  }
  closest(selector) {
    for (let node = this; node; node = node.parent) if (node.matches(selector)) return node;
    return null;
  }
  matches(selector) {
    if (selector.startsWith(".")) return this.className?.split(" ").includes(selector.slice(1)) || this.classes.has(selector.slice(1));
    if (selector.startsWith("[")) return this.hasAttribute(selector.slice(1, -1));
    return this.tag === selector;
  }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  querySelectorAll(selector) {
    const tags = selector.split(",").map(s => s.trim());
    return this.children.flatMap(child => [
      ...(tags.some(tag => child.matches(tag)) ? [child] : []), ...child.querySelectorAll(selector)
    ]);
  }
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const loc = (id, name) => ({ id, name, address: "Dirección de test", pos_x: 0.2, pos_y: 0.8, is_demo: true });
const button = (row, text) => row.querySelectorAll("button").find(node => node.textContent === text);

async function adminHarness() {
  const source = fs.readFileSync(path.join(root, "static/js/admin.js"), "utf8");
  const ids = Object.fromEntries([...source.matchAll(/getElementById\("([^"]+)"\)/g)].map(match => [match[1], new Node()]));
  const requests = [], scenes = [];
  const document = {
    readyState: "complete", activeElement: null, hidden: false,
    getElementById: id => ids[id], querySelectorAll: () => [],
    createElement: tag => new Node(tag)
  };
  const window = {
    location: { hash: "", assign: () => assert.fail("No debe redirigir") },
    addEventListener() {}, clearTimeout() {}, setTimeout() {},
    OpleCity: { render: data => scenes.push(data), select() {} }
  };
  vm.runInNewContext(source, {
    document, window,
    fetch: (url, options) => new Promise(resolve => requests.push({ url, options, resolve }))
  }, { filename: "admin.js" });
  function respond(request, data) {
    request.resolve({ status: 200, ok: true, json: () => Promise.resolve(data) });
  }
  respond(requests[0], { authenticated: true, csrf_token: "test-token", user: { email: "test@example.com" } });
  await flush();
  for (const request of requests.slice(1)) {
    respond(request, request.url === "/api/dashboard" ? {
      tasks_pending: 0, tasks_completed: 0, products: 0, locations: 1, products_by_category: []
    } : request.url === "/api/locations" ? [loc(1, "Inicial")] : []);
  }
  await flush();
  return { ids, requests, scenes, respond };
}

test("Cancelar dos ediciones: la respuesta vieja no sobrescribe lista, escena ni estado vacío", async () => {
  const h = await adminHarness();
  const row = h.ids["location-list"].children[0];
  button(row, "Editar").click();
  // Ambos callbacks son reales y comparten refreshVersion: no hay refresh entre ellos.
  button(row, "Cancelar").click();
  button(row, "Cancelar").click();
  const [old, recent] = h.requests.slice(-2);
  assert.equal(old.url, "/api/locations");
  assert.equal(recent.url, "/api/locations");
  h.respond(recent, [loc(2, "Más reciente")]);
  await flush();
  h.respond(old, []);
  await flush();
  assert.equal(h.ids["location-list"].children[0].dataset.id, 2);
  assert.equal(h.ids["locations-empty"].hidden, true);
  assert.equal(h.scenes.at(-1)[0].name, "Más reciente");
  assert.equal(h.scenes.length, 2, "La consulta obsoleta no redibuja la escena");
});

test("La respuesta reciente vacía tampoco es sustituida por registros antiguos", async () => {
  const h = await adminHarness();
  const row = h.ids["location-list"].children[0];
  button(row, "Editar").click();
  button(row, "Cancelar").click();
  button(row, "Cancelar").click();
  const [old, recent] = h.requests.slice(-2);
  h.respond(recent, []);
  await flush();
  h.respond(old, [loc(3, "Obsoleta")]);
  await flush();
  assert.equal(h.ids["location-list"].children.length, 0);
  assert.equal(h.ids["locations-empty"].hidden, false);
  assert.equal(h.scenes.at(-1).length, 0);
});

test("Guardar edición: campos vacíos/espacios/incorrectos no envían PATCH; cero y uno sí", async () => {
  const h = await adminHarness();
  const row = h.ids["location-list"].children[0];
  button(row, "Editar").click();
  const [,, x, y] = row.querySelectorAll("input");
  assert.equal(x.required, true);
  assert.equal(y.required, true);
  const count = h.requests.length;
  for (const [rawX, rawY] of [["", "0.8"], ["0.2", ""], ["   ", "1"], ["0", "\t"], ["bad", "1"], ["-0.1", "1"], ["0", "1.01"]]) {
    x.value = rawX; y.value = rawY;
    button(row, "Guardar").click();
    assert.equal(h.requests.length, count, `No enviar (${rawX}, ${rawY})`);
    assert.equal(h.ids.toast.hidden, false);
  }
  x.value = "0"; y.value = "1";
  button(row, "Guardar").click();
  assert.equal(h.requests.length, count + 1);
  const request = h.requests.at(-1);
  assert.equal(request.options.method, "PATCH");
  assert.equal(request.options.headers["X-CSRF-Token"], "test-token");
  assert.deepEqual(JSON.parse(request.options.body), {
    name: "Inicial", address: "Dirección de test", pos_x: 0, pos_y: 1, is_demo: true
  });
});

function project(x, y, z, scale, tilt, rotation) {
  const r = rotation * Math.PI / 180, t = tilt * Math.PI / 180;
  const rx = x * Math.cos(r) - y * Math.sin(r);
  const ry = x * Math.sin(r) + y * Math.cos(r);
  const py = (ry * Math.cos(t) - z * Math.sin(t)) * scale;
  const pz = (ry * Math.sin(t) + z * Math.cos(t)) * scale;
  const perspective = geometry.perspective / (geometry.perspective - pz);
  return [rx * scale * perspective, py * perspective];
}

test("Geometría sin 3D: tablero y pines extremos/foco caben en ancho Y alto", () => {
  for (const [width, height] of [[1100, 360], [580, 360], [320, 360], [240, 360], [200, 180]]) {
    const scale = city.fitScene(width, height, true, geometry);
    assert.ok(scale > 0 && scale <= 1);
    assert.ok(geometry.extent * scale <= width / 2 - geometry.clearance + 1e-8);
    assert.ok(geometry.extent * scale <= height / 2 - geometry.clearance + 1e-8);
    for (const x of [0, 1]) for (const y of [0, 1]) {
      const p = city.position({ pos_x: x, pos_y: y });
      // 34px de restaurante + 8px de foco en cada extremo.
      const halfPin = 34 / 2 + 8;
      for (const dx of [-halfPin, halfPin]) for (const dy of [-halfPin, halfPin]) {
        assert.ok(Math.abs((p.x / 100 * boardSize - boardSize / 2 + dx) * scale) < width / 2);
        assert.ok(Math.abs((p.y / 100 * boardSize - boardSize / 2 + dy) * scale) < height / 2);
      }
    }
  }
});

test("Geometría 3D: perspectiva y todas las rotaciones caben, incluidos cubos altos y selección", () => {
  for (const [width, height] of [[1100, 840], [580, 600], [320, 460], [1100, 460], [580, 460], [320, 340], [240, 340]]) {
    const scale = city.fitScene(width, height, false, geometry);
    for (let rotation = -180; rotation <= 180; rotation += 5) {
      for (let tilt = 0; tilt <= 70; tilt += 5) {
        // Caja envolvente mayor que tablero, decoraciones, restaurantes y foco.
        for (const x of [-geometry.extent, geometry.extent]) {
          for (const y of [-geometry.extent, geometry.extent]) {
            for (const z of [0, geometry.maxHeight]) {
              const [px, py] = project(x, y, z, scale, tilt, rotation);
              assert.ok(Math.abs(px) <= width / 2 - geometry.clearance + 1e-8);
              assert.ok(Math.abs(py) <= height / 2 - geometry.clearance + 1e-8);
            }
          }
        }
      }
    }
  }
});

test("Cambiar Sin 3D/restablecer y redimensionar usa dimensiones de stage, no solo card", () => {
  const card = new Node(), board = new Node(), stage = new Node(), decor = new Node();
  const tilt = new Node("input"), rotate = new Node("input"), reset = new Node("button"), flat = new Node("button");
  const nodes = { ".city-board": board, ".map-stage": stage, ".city-decor": decor,
    "[data-city-tilt]": tilt, "[data-city-rotate]": rotate, "[data-city-reset]": reset, "[data-city-flat]": flat };
  card.querySelector = selector => nodes[selector];
  card.clientWidth = 1100;
  stage.clientWidth = 1098;
  Object.defineProperty(stage, "clientHeight", { get: () => card.classList.contains("scene-flat") ? 360 : 460 });
  let resizeCallback, observed;
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/city.js"), "utf8"), {
    document: { readyState: "complete", createElement: tag => new Node(tag), addEventListener() {},
      querySelectorAll: selector => selector === ".city-card" ? [card] : [] },
    window: { getComputedStyle: () => ({ getPropertyValue: key => ({
      "--city-extent": geometry.extent, "--city-max-height": geometry.maxHeight,
      "--city-clearance": geometry.clearance, "--city-perspective": geometry.perspective
    })[key] }) },
    ResizeObserver: class { constructor(callback) { resizeCallback = callback; } observe(node) { observed = node; } }
  });
  assert.equal(observed, stage);
  assert.equal(Number(board.style["--scale"]), city.fitScene(1098, 460, false, geometry));
  flat.click();
  assert.equal(Number(board.style["--scale"]), city.fitScene(1098, 360, true, geometry));
  assert.equal(tilt.disabled, true);
  stage.clientWidth = 240;
  resizeCallback();
  assert.equal(Number(board.style["--scale"]), city.fitScene(240, 360, true, geometry));
  flat.click();
  assert.equal(Number(board.style["--scale"]), city.fitScene(240, 460, false, geometry));
  reset.click();
  assert.equal(board.style["--tilt"], "58deg");
  assert.equal(board.style["--rotation"], "-32deg");
});

function panelCityHarness() {
  const card = new Node(), board = new Node(), stage = new Node(), decor = new Node(), pins = new Node();
  const tilt = new Node("input"), rotate = new Node("input"), reset = new Node("button"), flat = new Node("button");
  const note = new Node();
  const toolbar = new Node(), details = new Node("details"), summary = new Node("summary");
  card.className = "city-card";
  card.appendChild(toolbar);
  toolbar.appendChild(reset); toolbar.appendChild(flat);
  card.appendChild(stage); stage.appendChild(board); board.appendChild(decor); board.appendChild(pins);
  card.appendChild(note); card.appendChild(details); details.appendChild(summary);
  details.appendChild(tilt); details.appendChild(rotate);
  details.open = false;
  tilt.value = "58"; rotate.value = "-32";
  const nodes = { ".city-board": board, ".map-stage": stage, ".city-decor": decor,
    "[data-city-tilt]": tilt, "[data-city-rotate]": rotate, "[data-city-reset]": reset,
    "[data-city-flat]": flat };
  card.querySelector = selector => nodes[selector];
  card.querySelectorAll = selector => Node.prototype.querySelectorAll.call(card, selector);
  stage.clientWidth = 1000; stage.clientHeight = 800;
  const cards = [], events = {};
  const document = {
    readyState: "complete", activeElement: null, hidden: false, body: new Node(),
    createElement: tag => new Node(tag), addEventListener: (name, cb) => { events[name] = cb; },
    querySelectorAll: selector => ({
      ".city-card": [card], ".city-board": [board], ".city-pins": [pins], ".city-selection": [note],
      "[data-location-select]": [...pins.children, ...cards],
      ".city-decor .cuboid": decor.children
    })[selector] || []
  };
  const window = {
    addEventListener() {}, matchMedia: () => ({ matches: false }),
    getComputedStyle: node => ({ transform: `${node.style["--scale"]}/${node.style["--tilt"]}/${node.style["--rotation"]}`,
      getPropertyValue: key => ({ "--city-extent": geometry.extent, "--city-max-height": geometry.maxHeight,
        "--city-clearance": geometry.clearance, "--city-perspective": geometry.perspective })[key] })
  };
  card.ownerDocument = document;
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/city.js"), "utf8"), { document, window });
  return { window, document, events, cards, pins, note, tilt, rotate, reset, flat, board, details, summary, toolbar };
}

test("Panel: eliminar ID enfocado con details cerrado recupera reset visible y útil", () => {
  for (const remaining of [[], [loc(2, "Conservado")]]) {
    const h = panelCityHarness();
    h.window.OpleCity.render([loc(1, "Eliminar"), loc(2, "Conservado")]);
    const removed = h.pins.children[0];
    removed.focus();
    assert.equal(h.document.activeElement, removed);
    assert.equal(h.details.open, false);
    assert.equal(h.reset.getClientRects().length, 1, "Reset está fuera de details");
    h.window.OpleCity.render(remaining);
    assert.equal(h.document.activeElement, h.reset);
    assert.equal(h.reset.focusOptions.preventScroll, true);
    h.reset.click();
    assert.equal(h.board.style["--tilt"], "58deg", "El control recuperado sigue funcionando");
    assert.equal(h.details.open, false, "No abrir ajustes para recuperar el foco");
  }
});

test("Si el ID enfocado sigue presente, conserva foco en el nuevo botón de ese destino", () => {
  const h = panelCityHarness();
  h.window.OpleCity.render([loc(1, "Uno")]);
  const previous = h.pins.children[0]; previous.focus();
  h.window.OpleCity.render([loc(1, "Uno actualizado")]);
  assert.notEqual(h.document.activeElement, previous);
  assert.equal(h.document.activeElement, h.pins.children[0]);
});

test("Panel: sin botones elegibles usa summary visible, nunca reset oculto", () => {
  const admin = panelCityHarness();
  admin.window.OpleCity.render([loc(1, "Eliminar")]); admin.pins.children[0].focus();
  admin.window.OpleCity.render([]);
  assert.equal(admin.document.activeElement, admin.reset);
  admin.reset.click();
  assert.equal(admin.board.style["--rotation"], "-32deg");

  const h = panelCityHarness();
  h.details.appendChild(h.reset); h.flat.disabled = true;
  h.window.OpleCity.render([loc(1, "Eliminar")]); h.pins.children[0].focus();
  h.window.OpleCity.render([]);
  assert.equal(h.reset.getClientRects().length, 0);
  assert.equal(h.document.activeElement, h.summary);
  assert.equal(h.summary.getClientRects().length, 1);
});

test("Panel: selección sincroniza listado/escena y reinicia al vaciar sin alterar is_demo", () => {
  const h = panelCityHarness();
  h.window.OpleCity.render([]);
  assert.equal(h.pins.children.length, 0);
  assert.match(h.note.textContent, /Sin sucursales/);
  const locations = [loc(1, "Destino uno"), { ...loc(2, "Destino dos"), is_demo: false }];
  const original = JSON.stringify(locations);
  for (const entry of locations) {
    const card = new Node("button"); card.dataset.locationSelect = String(entry.id); h.cards.push(card);
  }
  h.window.OpleCity.render(locations);
  h.window.OpleCity.select(1);
  assert.equal(h.cards[0].getAttribute("aria-pressed"), "true");
  assert.equal(h.pins.children[0].getAttribute("aria-pressed"), "true");
  h.window.OpleCity.select(2);
  assert.equal(h.cards[0].getAttribute("aria-pressed"), "false");
  assert.equal(h.cards[1].getAttribute("aria-pressed"), "true");
  assert.match(h.note.textContent, /Destino dos.*Dirección/);
  h.window.OpleCity.select(1);
  assert.equal(h.cards[0].getAttribute("aria-pressed"), "true");
  h.pins.children[1].click();
  assert.equal(h.cards[1].getAttribute("aria-pressed"), "true");
  assert.equal(JSON.stringify(locations), original);
  h.window.OpleCity.render([]);
  assert.equal(h.pins.children.length, 0);
  assert.equal(h.cards[1].getAttribute("aria-pressed"), "false");
});

test("Panel: ocultar página activa pausa CSS sin modificar selección", () => {
  const h = panelCityHarness();
  h.document.hidden = true; h.events.visibilitychange();
  assert.equal(h.document.body.classList.contains("page-hidden"), true);
});

test("Landing: todos los destinos son ficticios y direcciones secundarias, sin modificar datos", async () => {
  const list = new Node(), count = new Node(), empty = new Node();
  const data = [loc(1, "Primero"), { ...loc(2, "Segundo"), is_demo: false }];
  const original = JSON.stringify(data);
  const ids = { "locations-list": list, "catalog-count": count, "locations-empty": empty };
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/landing.js"), "utf8"), {
    document: { readyState: "complete", createElement: tag => new Node(tag), getElementById: id => ids[id], querySelectorAll: () => [] },
    window: {},
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(data) })
  });
  await flush();
  assert.equal(list.children.length, 2);
  for (const row of list.children) {
    assert.match(row.children[0].textContent, /DESTINO FICTICIO/);
    assert.equal(row.children.at(-1).tag, "details");
    assert.equal(row.children.at(-1).children.at(-1).textContent, "Dirección de test");
    assert.equal(row.querySelectorAll("button, input").length, 0);
  }
  assert.equal(JSON.stringify(data), original);
  assert.equal(empty.hidden, true);
});

test("Landing vacía no fabrica destinos y mantiene un estado vacío claro", async () => {
  const list = new Node(), count = new Node(), empty = new Node();
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/landing.js"), "utf8"), {
    document: { readyState: "complete", createElement: tag => new Node(tag), querySelectorAll: () => [],
      getElementById: id => ({ "locations-list": list, "catalog-count": count, "locations-empty": empty })[id] },
    window: {},
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
  });
  await flush();
  assert.equal(list.children.length, 0);
  assert.equal(empty.hidden, false);
  assert.equal(count.textContent, "0 espacios en el catálogo");
});

function ambientHarness(reducedInitially = false, fail = false, withObserver = false) {
  const ground = new Node(), toggle = new Node("button"), list = new Node(), empty = new Node(), count = new Node();
  const media = { matches: reducedInitially, addEventListener(name, callback) { this.change = callback; } };
  const events = {};
  const landscape = new Node(), observers = [];
  const document = { readyState: "complete", body: new Node(), hidden: false,
    createElement: tag => new Node(tag), addEventListener: (name, cb) => { events[name] = cb; },
    getElementById: id => ({ "urban-buildings": ground, "ambient-toggle": toggle, "mapa": landscape,
      "locations-list": list, "locations-empty": empty, "catalog-count": count })[id] };
  const context = {
    document, window: { matchMedia: () => media },
    fetch: () => fail ? Promise.reject(new Error("offline")) : Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
  };
  if (withObserver) context.IntersectionObserver = class {
    constructor(callback, options) { this.callback = callback; this.options = options; observers.push(this); }
    observe(target) { this.target = target; }
    emit(visible) { this.callback([{ target: this.target, isIntersecting: visible }]); }
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/landing.js"), "utf8"), context);
  return { ground, toggle, list, empty, count, media, document, events, landscape, observers };
}

test("Paisaje: 70 volúmenes grandes sin foco ni IDs, independiente de API vacía o fallida", async () => {
  for (const fail of [false, true]) {
    const h = ambientHarness(false, fail); await flush();
    assert.equal(h.ground.children.length, 70);
    assert.equal(h.ground.querySelectorAll("button, input, a, summary").length, 0);
    assert.equal(h.list.children.length, 0);
    assert.equal(h.empty.hidden, false);
    assert.equal(h.ground.children.filter(node => node.className.includes("urban-pavilion")).length, 6);
    for (const node of h.ground.children) {
      assert.equal(node.children.length, 5);
      assert.ok(parseFloat(node.style["--w"]) >= 72);
      assert.ok(parseFloat(node.style["--h"]) >= 62);
      assert.equal(node.hasAttribute("tabindex"), false);
      assert.equal(node.dataset.locationSelect, undefined);
    }
  }
});

test("Ambiente: pausa manual, pestaña oculta y cambios de movimiento reducido mantienen estados coherentes", () => {
  const h = ambientHarness();
  assert.equal(h.toggle.hidden, false);
  assert.equal(h.document.body.classList.contains("ambient-ready"), true);
  h.toggle.click();
  assert.equal(h.toggle.getAttribute("aria-pressed"), "true");
  assert.equal(h.document.body.classList.contains("ambient-paused"), true);
  h.document.hidden = true; h.events.visibilitychange();
  assert.equal(h.document.body.classList.contains("page-hidden"), true);
  h.document.hidden = false; h.events.visibilitychange();
  assert.equal(h.document.body.classList.contains("ambient-paused"), true);
  h.media.matches = true; h.media.change();
  assert.equal(h.toggle.disabled, true);
  h.media.matches = false; h.media.change();
  assert.equal(h.toggle.disabled, false);
  assert.equal(h.toggle.getAttribute("aria-pressed"), "true", "Conserva pausa manual");
  h.toggle.click();
  assert.equal(h.document.body.classList.contains("ambient-paused"), false);
  assert.equal(h.toggle.textContent, "Pausar ambiente");
  const reduced = ambientHarness(true);
  assert.equal(reduced.toggle.getAttribute("aria-pressed"), "true");
  assert.equal(reduced.document.body.classList.contains("ambient-paused"), true);
});

test("Paisaje offscreen: Observer pausa solo el decorado y nunca anula pausa manual/reduce/hidden", () => {
  const h = ambientHarness(false, false, true);
  assert.equal(h.observers.length, 1);
  const observer = h.observers[0];
  assert.equal(observer.target, h.landscape);
  assert.equal(h.landscape.classList.contains("ambient-offscreen"), true);
  observer.emit(true);
  assert.equal(h.landscape.classList.contains("ambient-offscreen"), false);
  assert.equal(h.toggle.getAttribute("aria-pressed"), "false");
  h.toggle.click();
  observer.emit(false); observer.emit(true);
  assert.equal(h.document.body.classList.contains("ambient-paused"), true);
  assert.equal(h.toggle.getAttribute("aria-pressed"), "true");
  h.toggle.click();
  h.media.matches = true; h.media.change();
  observer.emit(false); observer.emit(true);
  assert.equal(h.document.body.classList.contains("ambient-paused"), true);
  assert.equal(h.toggle.disabled, true);
  h.document.hidden = true; h.events.visibilitychange();
  h.media.matches = false; h.media.change();
  observer.emit(true);
  assert.equal(h.document.body.classList.contains("page-hidden"), true);
  assert.equal(h.document.body.classList.contains("ambient-paused"), false);
});

test("Sin IntersectionObserver el ambiente conserva controles seguros sin pausa local permanente", () => {
  const h = ambientHarness();
  assert.equal(h.observers.length, 0);
  assert.equal(h.landscape.classList.contains("ambient-offscreen"), false);
  h.toggle.click();
  assert.equal(h.document.body.classList.contains("ambient-paused"), true);
  h.toggle.click();
  assert.equal(h.document.body.classList.contains("ambient-paused"), false);
});

test("Ventanas: la regla CSS anima solo la fachada frontal, 70 capas en lugar de 280", () => {
  const h = ambientHarness();
  // Se inspecciona la regla aplicada, no solo la existencia de un nombre de clase.
  const rules = [...cityCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(match => /animation:\s*windows-breathe/.test(match[2]));
  assert.equal(rules.length, 1);
  assert.equal(rules[0][1].trim().split("\n").at(-1), ".urban-block .front");
  const animated = h.ground.children.flatMap(node => node.children).filter(face => face.className.split(" ").includes("front"));
  assert.equal(animated.length, 70);
  assert.ok(h.ground.children.every(node => node.children.length === 5), "No quitar volumen o iluminación estática");
});

function chatHarness(context = "public", initiallyOpen = false) {
  const ids = Object.fromEntries(["chat-toggle", "chat-panel", "chat-close", "chat-form", "chat-input", "chat-send", "chat-status", "chat-messages", "chat-title", "chat-subtitle", "chat-toggle-label", "toast"].map(id => [id, new Node()]));
  const widget = new Node(), placeholder = new Node("p"), requests = [];
  widget.setAttribute("data-chat-context", context);
  widget.appendChild(ids["chat-panel"]);
  ids["chat-panel"].hidden = !initiallyOpen;
  placeholder.className = "chat-placeholder";
  ids["chat-messages"].appendChild(placeholder);
  ids["chat-messages"].querySelector = selector => ids["chat-messages"].querySelectorAll(selector)[0] || null;
  placeholder.remove = () => { ids["chat-messages"].replaceChildren(); };
  const window = { clearTimeout() {}, setTimeout() {} };
  vm.runInNewContext(fs.readFileSync(path.join(root, "static/js/chat.js"), "utf8"), {
    document: { readyState: "complete", getElementById: id => ids[id], createElement: tag => new Node(tag), addEventListener() {} },
    window, fetch: (url, options) => new Promise(resolve => requests.push({ url, options, resolve }))
  });
  return { ids, placeholder, requests, window,
    submit: text => { ids["chat-input"].value = text; ids["chat-form"].events.submit({ preventDefault() {} }); },
    respond: (status, data) => { requests.at(-1).resolve({ ok: status === 200, status, json: () => Promise.resolve(data) }); } };
}

test("Chat público: no consulta sesión y fija Mr. Mesi sin S antes del primer envío", async () => {
  const h = chatHarness("public", true), { ids } = h;
  assert.equal(h.requests.length, 0, "No GET sesión: contexto independiente de autenticación");
  assert.equal(ids["chat-title"].textContent, "Mr. Mesi sin S");
  assert.equal(ids["chat-toggle-label"].textContent, "Mr. Mesi sin S");
  assert.equal(ids["chat-subtitle"].textContent, "Asistente de Oplesktaurant");
  assert.equal(ids["chat-input"].getAttribute("aria-label"), "Mensaje para Mr. Mesi sin S");
  assert.equal(ids["chat-toggle"].getAttribute("aria-label"), "Cerrar asistente Mr. Mesi sin S");
  assert.match(h.placeholder.textContent, /Oplesktaurant/);
  h.submit("hola");
  assert.equal(h.requests[0].url, "/api/chat");
  assert.equal(JSON.parse(h.requests[0].options.body).context, "public");
  assert.equal(ids["chat-input"].disabled, true);
  h.submit("doble envío");
  assert.equal(h.requests.length, 1);
  h.respond(200, { identity: "mesi", reply: "Hola que mira bobo." }); await flush();
  assert.equal(ids["chat-input"].disabled, false);
  assert.equal(ids["chat-status"].textContent, "");
  assert.equal(ids["chat-toggle"].getAttribute("aria-label"), "Cerrar asistente Mr. Mesi sin S");
  h.submit("otro");
  const payload = JSON.parse(h.requests.at(-1).options.body);
  assert.equal(payload.history.length, 2);
  assert.equal(payload.history[1].content, "Hola que mira bobo.");
  h.respond(200, { identity: "nbapeh", reply: "No debe aparecer" }); await flush();
  assert.equal(ids["chat-title"].textContent, "Mr. Mesi sin S");
  assert.ok(!ids["chat-messages"].children.some(node => node.textContent === "No debe aparecer"));
  assert.match(ids["chat-status"].textContent, /no corresponde/);
  assert.equal(ids["chat-send"].disabled, false);
});

test("Chat admin: contexto fijo, error 401 claro y no cambia identidad ni mezcla historial", async () => {
  const h = chatHarness("admin"), { ids } = h;
  assert.equal(ids["chat-title"].textContent, "Nbapeh");
  assert.equal(ids["chat-toggle"].getAttribute("aria-label"), "Abrir asistente Nbapeh");
  h.window.OpleChat.open();
  h.submit("ayuda");
  assert.equal(JSON.parse(h.requests[0].options.body).context, "admin");
  h.respond(200, { identity: "nbapeh", reply: "Consulta inventario." }); await flush();
  assert.equal(ids["chat-toggle"].getAttribute("aria-label"), "Cerrar asistente Nbapeh");
  h.submit("otra pregunta");
  h.respond(401, { error: "expired" }); await flush();
  assert.match(ids["chat-status"].textContent, /sesión.*expirado/);
  assert.equal(ids["chat-title"].textContent, "Nbapeh");
  assert.equal(ids["chat-input"].disabled, true);
  assert.equal(ids["chat-send"].disabled, true);
  h.submit("no enviar");
  assert.equal(h.requests.length, 2);
  h.window.OpleChat.close(true);
  assert.equal(ids["chat-toggle"].getAttribute("aria-label"), "Abrir asistente Nbapeh");
});

test("Chat errores transitorios libera busy sin alterar contexto", async () => {
  const h = chatHarness("public"); h.submit("hola");
  h.respond(429, { error: "Espera un minuto." }); await flush();
  assert.equal(h.ids["chat-send"].disabled, false);
  assert.equal(h.ids["chat-title"].textContent, "Mr. Mesi sin S");
  assert.equal(h.ids["chat-status"].textContent, "Espera un minuto.");
});

test("Paleta: contraste texto 4.5:1 y controles/gráficas 3:1 sobre superficies", () => {
  const css = fs.readFileSync(path.join(root, "static/css/style.css"), "utf8");
  const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)].map(m => [m[1], m[2]]));
  function luminance(hex) {
    const [r, g, b] = hex.slice(1).match(/../g).map(n => parseInt(n, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return .2126 * r + .7152 * g + .0722 * b;
  }
  function contrast(a, b) { const la = luminance(a), lb = luminance(b); return (Math.max(la, lb) + .05) / (Math.min(la, lb) + .05); }
  for (const surface of ["bg", "panel", "surface", "surface-raised", "surface-hover"]) {
    for (const text of ["ink", "muted", "accent", "accent-2"]) assert.ok(contrast(tokens[text], tokens[surface]) >= 4.5, `${text}/${surface}`);
    assert.ok(contrast(tokens.line, tokens[surface]) >= 3, `borde/${surface}`);
  }
  assert.ok(contrast(tokens["accent-ink"], tokens.accent) >= 4.5);
  for (const bar of ["chart-pending", "chart-completed", "accent-4"]) assert.ok(contrast(tokens[bar], tokens["chart-track"]) >= 3);
});
