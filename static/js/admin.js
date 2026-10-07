/* Oplestaurants - panel administrativo (tareas, inventario, ubicaciones). */
(function () {
  "use strict";

  var csrfToken = "";

  // ---- Utilidades --------------------------------------------------------

  function toast(message, isError) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    el.classList.toggle("error", !!isError);
    window.clearTimeout(el._timer);
    el._timer = window.setTimeout(function () { el.hidden = true; }, 3500);
  }

  function api(path, options) {
    options = options || {};
    var method = options.method || "GET";
    var headers = { "Content-Type": "application/json", "Accept": "application/json" };
    if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;
    return fetch(path, {
      method: method,
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    }).then(function (res) {
      if (res.status === 401) {
        window.location.assign("/login?next=/admin");
        throw new Error("Sesión expirada.");
      }
      if (res.status === 204) return null;
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          throw new Error((data && data.error) || ("Error HTTP " + res.status));
        }
        return data;
      });
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function formatQuantity(value) {
    var n = Number(value);
    if (!isFinite(n)) return String(value);
    return String(n);
  }

  var SVG_NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  // Gráfica de barras horizontales basada solo en datos reales.
  function renderBarChart(container, items) {
    if (!container) return;
    container.innerHTML = "";
    if (!items.length) {
      container.appendChild(el("p", "chart-empty", "Sin datos todavía."));
      return;
    }
    var max = items.reduce(function (acc, it) { return Math.max(acc, it.value); }, 0) || 1;
    var rowH = 30;
    var width = 300;
    var labelW = 110;
    var height = items.length * rowH + 6;
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": "Gráfica de datos reales"
    });
    items.forEach(function (it, i) {
      var y = i * rowH + 4;
      var barW = Math.max(2, (it.value / max) * (width - labelW - 40));
      var label = svgEl("text", {
        x: 0, y: y + 15, "font-size": "12",
        "font-family": "system-ui, sans-serif", fill: "#334155"
      });
      label.textContent = it.label.length > 16 ? it.label.slice(0, 15) + "…" : it.label;
      svg.appendChild(label);
      svg.appendChild(svgEl("rect", {
        x: labelW, y: y + 4, width: barW, height: 16, rx: 4,
        fill: it.color || "#e11d48"
      }));
      var value = svgEl("text", {
        x: labelW + barW + 6, y: y + 16, "font-size": "12", "font-weight": "700",
        "font-family": "system-ui, sans-serif", fill: "#0f172a"
      });
      value.textContent = String(it.value);
      svg.appendChild(value);
    });
    container.appendChild(svg);
  }

  // ---- Dashboard ---------------------------------------------------------

  function loadDashboard() {
    return api("/api/dashboard").then(function (data) {
      document.getElementById("m-pending").textContent = data.tasks_pending;
      document.getElementById("m-completed").textContent = data.tasks_completed;
      document.getElementById("m-products").textContent = data.products;
      document.getElementById("m-locations").textContent = data.locations;

      renderBarChart(document.getElementById("chart-tasks"), [
        { label: "Pendientes", value: data.tasks_pending, color: "#f59e0b" },
        { label: "Completadas", value: data.tasks_completed, color: "#22c55e" }
      ]);
      var palette = ["#e11d48", "#0ea5e9", "#22c55e", "#f59e0b", "#8b5cf6", "#14b8a6"];
      var categories = (data.products_by_category || []).map(function (item, i) {
        return { label: item.category, value: item.count, color: palette[i % palette.length] };
      });
      renderBarChart(document.getElementById("chart-products"), categories);
    }).catch(function (err) { toast(err.message, true); });
  }

  // ---- Tareas ------------------------------------------------------------

  function renderTask(task) {
    var li = el("li", "item");
    li.dataset.id = task.id;
    var main = el("div", "item-main");
    main.appendChild(el("div", "item-title", task.title));
    if (task.description) main.appendChild(el("div", "item-desc", task.description));
    li.appendChild(main);

    li.appendChild(el("span", "badge" + (task.status === "completed" ? " completed" : ""),
      task.status === "completed" ? "Completada" : "Pendiente"));

    var actions = el("div", "actions");
    var toggle = el("button", "secondary", task.status === "completed" ? "Reabrir" : "Completar");
    toggle.type = "button";
    toggle.addEventListener("click", function () {
      updateTask(task.id, { status: task.status === "completed" ? "pending" : "completed" });
    });
    actions.appendChild(toggle);

    var edit = el("button", "secondary", "Editar");
    edit.type = "button";
    edit.addEventListener("click", function () { editTask(task, li); });
    actions.appendChild(edit);

    var del = el("button", "danger", "Eliminar");
    del.type = "button";
    del.addEventListener("click", function () { deleteTask(task.id); });
    actions.appendChild(del);

    li.appendChild(actions);
    return li;
  }

  function loadTasks() {
    var filter = document.getElementById("task-filter").value;
    var path = "/api/tasks" + (filter ? "?status=" + encodeURIComponent(filter) : "");
    return api(path).then(function (tasks) {
      var list = document.getElementById("task-list");
      list.innerHTML = "";
      tasks.forEach(function (t) { list.appendChild(renderTask(t)); });
      document.getElementById("tasks-empty").hidden = tasks.length !== 0;
    }).catch(function (err) { toast(err.message, true); });
  }

  function refresh() { loadDashboard(); loadTasks(); loadProducts(); loadLocations(); }

  function createTask(evt) {
    evt.preventDefault();
    var title = document.getElementById("task-title").value.trim();
    var description = document.getElementById("task-description").value.trim();
    if (!title) { toast("El título es obligatorio.", true); return; }
    api("/api/tasks", { method: "POST", body: { title: title, description: description || null } })
      .then(function () { document.getElementById("task-form").reset(); refresh(); })
      .catch(function (err) { toast(err.message, true); });
  }

  function updateTask(id, body) {
    api("/api/tasks/" + id, { method: "PATCH", body: body })
      .then(refresh).catch(function (err) { toast(err.message, true); });
  }

  function deleteTask(id) {
    api("/api/tasks/" + id, { method: "DELETE" })
      .then(refresh).catch(function (err) { toast(err.message, true); });
  }

  function editTask(task, li) {
    li.innerHTML = "";
    var main = el("div", "item-main");
    var titleInput = el("input", "edit-title");
    titleInput.type = "text";
    titleInput.maxLength = 200;
    titleInput.value = task.title;
    var descInput = el("input", "edit-desc");
    descInput.type = "text";
    descInput.value = task.description || "";
    main.appendChild(titleInput);
    main.appendChild(descInput);
    li.appendChild(main);

    var actions = el("div", "actions");
    var save = el("button", "", "Guardar");
    save.type = "button";
    save.addEventListener("click", function () {
      var title = titleInput.value.trim();
      if (!title) { toast("El título es obligatorio.", true); return; }
      updateTask(task.id, { title: title, description: descInput.value.trim() || null });
    });
    var cancel = el("button", "secondary", "Cancelar");
    cancel.type = "button";
    cancel.addEventListener("click", loadTasks);
    actions.appendChild(save);
    actions.appendChild(cancel);
    li.appendChild(actions);
    titleInput.focus();
  }

  // ---- Productos ---------------------------------------------------------

  function renderProduct(product) {
    var li = el("li", "item");
    li.dataset.id = product.id;
    var main = el("div", "item-main");
    main.appendChild(el("div", "item-title", product.name));
    var meta = product.unit + (product.category ? " · " + product.category : "");
    main.appendChild(el("div", "item-meta", meta));
    li.appendChild(main);

    li.appendChild(el("span", "item-meta",
      formatQuantity(product.quantity) + " " + product.unit));

    var actions = el("div", "actions");
    var deltaInput = el("input", "qty-input");
    deltaInput.type = "number";
    deltaInput.step = "0.001";
    deltaInput.value = "1";
    deltaInput.setAttribute("aria-label", "Ajuste de cantidad");
    actions.appendChild(deltaInput);

    var minus = el("button", "secondary", "−");
    minus.type = "button";
    minus.title = "Restar";
    minus.addEventListener("click", function () { adjust(product.id, deltaInput.value, -1); });
    actions.appendChild(minus);

    var plus = el("button", "secondary", "+");
    plus.type = "button";
    plus.title = "Sumar";
    plus.addEventListener("click", function () { adjust(product.id, deltaInput.value, 1); });
    actions.appendChild(plus);

    var edit = el("button", "secondary", "Editar");
    edit.type = "button";
    edit.addEventListener("click", function () { editProduct(product, li); });
    actions.appendChild(edit);

    var del = el("button", "danger", "Eliminar");
    del.type = "button";
    del.addEventListener("click", function () { deleteProduct(product.id); });
    actions.appendChild(del);

    li.appendChild(actions);
    return li;
  }

  function loadProducts() {
    return api("/api/products").then(function (products) {
      var list = document.getElementById("product-list");
      list.innerHTML = "";
      products.forEach(function (p) { list.appendChild(renderProduct(p)); });
      document.getElementById("products-empty").hidden = products.length !== 0;
    }).catch(function (err) { toast(err.message, true); });
  }

  function createProduct(evt) {
    evt.preventDefault();
    var name = document.getElementById("product-name").value.trim();
    var category = document.getElementById("product-category").value.trim();
    var unit = document.getElementById("product-unit").value.trim();
    var quantityRaw = document.getElementById("product-quantity").value;
    if (!name) { toast("El nombre es obligatorio.", true); return; }
    if (!unit) { toast("La unidad es obligatoria.", true); return; }
    var quantity = quantityRaw === "" ? 0 : Number(quantityRaw);
    if (!isFinite(quantity) || quantity < 0) { toast("Cantidad inválida.", true); return; }
    api("/api/products", {
      method: "POST",
      body: { name: name, category: category || null, unit: unit, quantity: quantity }
    }).then(function () {
      document.getElementById("product-form").reset();
      document.getElementById("product-quantity").value = "0";
      refresh();
    }).catch(function (err) { toast(err.message, true); });
  }

  function adjust(id, rawDelta, sign) {
    var magnitude = Number(rawDelta);
    if (!isFinite(magnitude) || magnitude < 0) { toast("Ajuste inválido.", true); return; }
    var delta = sign * magnitude;
    if (delta === 0) { toast("El ajuste no puede ser 0.", true); return; }
    api("/api/products/" + id + "/quantity", { method: "POST", body: { delta: delta } })
      .then(refresh).catch(function (err) { toast(err.message, true); });
  }

  function deleteProduct(id) {
    api("/api/products/" + id, { method: "DELETE" })
      .then(refresh).catch(function (err) { toast(err.message, true); });
  }

  function editProduct(product, li) {
    li.innerHTML = "";
    var main = el("div", "item-main");
    var nameInput = el("input");
    nameInput.type = "text";
    nameInput.maxLength = 200;
    nameInput.value = product.name;
    var catInput = el("input");
    catInput.type = "text";
    catInput.value = product.category || "";
    var unitInput = el("input");
    unitInput.type = "text";
    unitInput.maxLength = 50;
    unitInput.value = product.unit;
    main.appendChild(nameInput);
    main.appendChild(catInput);
    main.appendChild(unitInput);
    li.appendChild(main);

    var actions = el("div", "actions");
    var save = el("button", "", "Guardar");
    save.type = "button";
    save.addEventListener("click", function () {
      var name = nameInput.value.trim();
      var unit = unitInput.value.trim();
      if (!name) { toast("El nombre es obligatorio.", true); return; }
      if (!unit) { toast("La unidad es obligatoria.", true); return; }
      api("/api/products/" + product.id, {
        method: "PATCH",
        body: { name: name, category: catInput.value.trim() || null, unit: unit }
      }).then(refresh).catch(function (err) { toast(err.message, true); });
    });
    var cancel = el("button", "secondary", "Cancelar");
    cancel.type = "button";
    cancel.addEventListener("click", loadProducts);
    actions.appendChild(save);
    actions.appendChild(cancel);
    li.appendChild(actions);
    nameInput.focus();
  }

  // ---- Ubicaciones -------------------------------------------------------

  function renderLocation(loc) {
    var li = el("li", "item");
    li.dataset.id = loc.id;
    var main = el("div", "item-main");
    main.appendChild(el("div", "item-title", loc.name));
    main.appendChild(el("div", "item-desc", loc.address));
    main.appendChild(el("div", "item-meta",
      "posición normalizada: x=" + loc.pos_x + ", y=" + loc.pos_y));
    li.appendChild(main);

    if (loc.is_demo) li.appendChild(el("span", "badge demo", "Demo"));

    var actions = el("div", "actions");
    var edit = el("button", "secondary", "Editar");
    edit.type = "button";
    edit.addEventListener("click", function () { editLocation(loc, li); });
    actions.appendChild(edit);
    var del = el("button", "danger", "Eliminar");
    del.type = "button";
    del.addEventListener("click", function () { deleteLocation(loc.id); });
    actions.appendChild(del);
    li.appendChild(actions);
    return li;
  }

  function loadLocations() {
    return api("/api/locations").then(function (locations) {
      var list = document.getElementById("location-list");
      list.innerHTML = "";
      locations.forEach(function (loc) { list.appendChild(renderLocation(loc)); });
      document.getElementById("locations-empty").hidden = locations.length !== 0;
    }).catch(function (err) { toast(err.message, true); });
  }

  function createLocation(evt) {
    evt.preventDefault();
    var name = document.getElementById("location-name").value.trim();
    var address = document.getElementById("location-address").value.trim();
    var x = Number(document.getElementById("location-x").value);
    var y = Number(document.getElementById("location-y").value);
    var isDemo = document.getElementById("location-demo").checked;
    if (!name) { toast("El nombre es obligatorio.", true); return; }
    if (!address) { toast("La dirección es obligatoria.", true); return; }
    if (!isFinite(x) || x < 0 || x > 1 || !isFinite(y) || y < 0 || y > 1) {
      toast("La posición normalizada debe estar entre 0 y 1.", true);
      return;
    }
    api("/api/locations", {
      method: "POST",
      body: { name: name, address: address, pos_x: x, pos_y: y, is_demo: isDemo }
    }).then(function () {
      document.getElementById("location-form").reset();
      refresh();
    }).catch(function (err) { toast(err.message, true); });
  }

  function deleteLocation(id) {
    api("/api/locations/" + id, { method: "DELETE" })
      .then(refresh).catch(function (err) { toast(err.message, true); });
  }

  function editLocation(loc, li) {
    li.innerHTML = "";
    var main = el("div", "item-main");
    var nameInput = el("input");
    nameInput.type = "text";
    nameInput.maxLength = 200;
    nameInput.value = loc.name;
    var addressInput = el("input");
    addressInput.type = "text";
    addressInput.maxLength = 300;
    addressInput.value = loc.address;
    var xInput = el("input");
    xInput.type = "number";
    xInput.min = "0";
    xInput.max = "1";
    xInput.step = "0.01";
    xInput.value = loc.pos_x;
    var yInput = el("input");
    yInput.type = "number";
    yInput.min = "0";
    yInput.max = "1";
    yInput.step = "0.01";
    yInput.value = loc.pos_y;
    main.appendChild(nameInput);
    main.appendChild(addressInput);
    main.appendChild(xInput);
    main.appendChild(yInput);
    li.appendChild(main);

    var actions = el("div", "actions");
    var save = el("button", "", "Guardar");
    save.type = "button";
    save.addEventListener("click", function () {
      var name = nameInput.value.trim();
      var address = addressInput.value.trim();
      var x = Number(xInput.value);
      var y = Number(yInput.value);
      if (!name) { toast("El nombre es obligatorio.", true); return; }
      if (!address) { toast("La dirección es obligatoria.", true); return; }
      if (!isFinite(x) || x < 0 || x > 1 || !isFinite(y) || y < 0 || y > 1) {
        toast("La posición normalizada debe estar entre 0 y 1.", true);
        return;
      }
      api("/api/locations/" + loc.id, {
        method: "PATCH",
        body: { name: name, address: address, pos_x: x, pos_y: y }
      }).then(refresh).catch(function (err) { toast(err.message, true); });
    });
    var cancel = el("button", "secondary", "Cancelar");
    cancel.type = "button";
    cancel.addEventListener("click", loadLocations);
    actions.appendChild(save);
    actions.appendChild(cancel);
    li.appendChild(actions);
    nameInput.focus();
  }

  // ---- Sesión / arranque -------------------------------------------------

  function bootstrap() {
    document.getElementById("task-form").addEventListener("submit", createTask);
    document.getElementById("product-form").addEventListener("submit", createProduct);
    document.getElementById("location-form").addEventListener("submit", createLocation);
    document.getElementById("task-filter").addEventListener("change", loadTasks);

    var logout = document.getElementById("logout-btn");
    if (logout) {
      logout.addEventListener("click", function () {
        api("/api/session", { method: "DELETE" }).then(function () {
          window.location.assign("/login");
        }).catch(function () { window.location.assign("/login"); });
      });
    }

    api("/api/session").then(function (data) {
      if (!data || !data.authenticated) {
        window.location.assign("/login?next=/admin");
        return;
      }
      csrfToken = data.csrf_token || "";
      var emailEl = document.getElementById("admin-email");
      if (emailEl && data.user) emailEl.textContent = data.user.email;
      refresh();
    }).catch(function () {
      window.location.assign("/login?next=/admin");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
