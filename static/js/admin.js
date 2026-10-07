/* Oplesktaurant - panel administrativo (tareas, inventario, ubicaciones). */
(function () {
  "use strict";

  var csrfToken = "";
  var productsCache = [];
  var refreshVersion = 0;

  function stockSummary(products) {
    return { total: products.length, zero: products.filter(function (p) { return Number(p.quantity) === 0; }).length };
  }

  function taskDistribution(pending, completed) {
    var total = pending + completed;
    return { total: total, completedPercent: total ? completed / total * 100 : 0 };
  }

  function formatCreated(value) {
    var date = new Date(value);
    return value && !isNaN(date.getTime()) ? date.toLocaleDateString("es", { day: "2-digit", month: "short", year: "numeric" }) : "Sin fecha";
  }

  function labelInput(parent, input, text) {
    var label = el("label", "edit-field", text);
    label.appendChild(input);
    parent.appendChild(label);
  }

  function replaceList(list, items, renderer) {
    var active = document.activeElement;
    var row = active && list.contains(active) ? active.closest("li[data-id]") : null;
    var id = row ? row.dataset.id : null;
    var text = active ? active.textContent : "";
    var label = active ? active.getAttribute("aria-label") : null;
    list.replaceChildren();
    items.forEach(function (item) { list.appendChild(renderer(item)); });
    if (!row) return;
    var nextRow = Array.from(list.children).find(function (item) { return item.dataset.id === id; });
    var next = nextRow && Array.from(nextRow.querySelectorAll("button, input")).find(function (item) {
      return label ? item.getAttribute("aria-label") === label : item.textContent === text;
    });
    // Tras editar/eliminar, mantener el foco del teclado fuera del body.
    (next || list.closest("section")).focus({ preventScroll: true });
  }

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

  // Barras HTML: cada valor sigue legible sin estilos ni animación.
  function renderBarChart(container, items) {
    if (!container) return;
    container.innerHTML = "";
    if (!items.length) {
      container.appendChild(el("p", "chart-empty", "Sin datos todavía."));
      return;
    }
    var max = items.reduce(function (acc, it) { return Math.max(acc, it.value); }, 0) || 1;
    var list = el("ul", "bar-chart");
    items.forEach(function (it) {
      var row = el("li");
      var label = el("div", "bar-label");
      label.appendChild(el("span", "", it.label));
      label.appendChild(el("strong", "", it.value));
      var track = el("div", "bar-track");
      track.setAttribute("aria-hidden", "true");
      var fill = el("div", "bar-fill");
      fill.style.width = (it.value / max * 100) + "%";
      fill.style.backgroundColor = it.color;
      track.appendChild(fill);
      row.appendChild(label); row.appendChild(track); list.appendChild(row);
    });
    container.appendChild(list);
  }

  function renderDonut(container, pending, completed) {
    container.replaceChildren();
    var stats = taskDistribution(pending, completed);
    var layout = el("div", "donut-layout");
    var donut = el("div", "donut");
    donut.setAttribute("aria-hidden", "true");
    donut.style.background = stats.total ? "conic-gradient(var(--chart-completed) 0 " + stats.completedPercent + "%, var(--chart-pending) " + stats.completedPercent + "% 100%)" : "var(--chart-track)";
    var center = el("div", "donut-center");
    center.appendChild(el("strong", "", stats.total));
    center.appendChild(el("span", "", "tareas"));
    donut.appendChild(center); layout.appendChild(donut);
    var legend = el("ul", "chart-legend");
    [{ label: "Pendientes", value: pending, color: "var(--chart-pending)" }, { label: "Completadas", value: completed, color: "var(--chart-completed)" }].forEach(function (item) {
      var row = el("li");
      var dot = el("span", "legend-dot");
      dot.style.backgroundColor = item.color;
      dot.setAttribute("aria-hidden", "true");
      row.appendChild(dot); row.appendChild(el("span", "", item.label)); row.appendChild(el("strong", "", item.value)); legend.appendChild(row);
    });
    layout.appendChild(legend); container.appendChild(layout);
    container.appendChild(el("p", "chart-caption", stats.total ? stats.completedPercent.toLocaleString("es", { maximumFractionDigits: 1 }) + "% de las tareas registradas están completadas." : "Sin tareas registradas. No hay distribución que calcular."));
  }

  function setMetric(id, value) {
    var node = document.getElementById(id);
    if (node.textContent === String(value)) return;
    node.textContent = value;
    // El texto siempre muestra el dato real; solo animamos su presentación.
    if (node.animate && !document.hidden && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      node.animate([{ opacity: .35, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 450 });
    }
  }

  // ---- Dashboard ---------------------------------------------------------

  function loadDashboard() {
    var version = refreshVersion;
    return api("/api/dashboard").then(function (data) {
      if (version !== refreshVersion) return;
      setMetric("m-pending", data.tasks_pending);
      setMetric("m-completed", data.tasks_completed);
      setMetric("m-products", data.products);
      setMetric("m-locations", data.locations);
      renderDonut(document.getElementById("chart-tasks"), data.tasks_pending, data.tasks_completed);
      var palette = ["var(--accent)", "var(--accent-2)", "var(--accent-3)", "var(--accent-4)", "var(--scene-window-warm)", "var(--scene-edge)"];
      var categories = (data.products_by_category || []).map(function (item, i) {
        return { label: item.category, value: item.count, color: palette[i % palette.length] };
      });
      renderBarChart(document.getElementById("chart-products"), categories);
    });
  }

  // ---- Tareas ------------------------------------------------------------

  function renderTask(task) {
    var li = el("li", "item");
    li.dataset.id = task.id;
    var main = el("div", "item-main");
    main.appendChild(el("div", "item-title", task.title));
    if (task.description) main.appendChild(el("div", "item-desc", task.description));
    main.appendChild(el("div", "item-meta", "Creada: " + formatCreated(task.created_at)));
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
    var version = ++taskLoadVersion;
    var filter = document.getElementById("task-filter").value;
    var path = "/api/tasks" + (filter ? "?status=" + encodeURIComponent(filter) : "");
    return api(path).then(function (tasks) {
      if (version !== taskLoadVersion) return;
      var list = document.getElementById("task-list");
      replaceList(list, tasks, renderTask);
      document.getElementById("tasks-empty").hidden = tasks.length !== 0;
    });
  }
  var taskLoadVersion = 0;
  function refresh() {
    var version = ++refreshVersion;
    var button = document.getElementById("refresh-btn");
    button.disabled = true;
    document.getElementById("sync-status").textContent = "Actualizando datos…";
    return Promise.allSettled([loadDashboard(), loadTasks(), loadProducts(), loadLocations()]).then(function (results) {
      if (version !== refreshVersion) return;
      button.disabled = false;
      var errors = results.filter(function (result) { return result.status === "rejected"; });
      document.getElementById("sync-status").textContent = errors.length ? "Actualización incompleta. Algunos datos pueden estar desactualizados." : "Consultado a las " + new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
      if (errors.length) toast(errors[0].reason.message, true);
    });
  }

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
    labelInput(main, titleInput, "Título");
    labelInput(main, descInput, "Descripción (opcional)");
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
    cancel.addEventListener("click", function () { loadTasks().catch(function (err) { toast(err.message, true); }); });
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

    li.appendChild(el("span", "item-meta quantity" + (Number(product.quantity) === 0 ? " zero" : ""),
      formatQuantity(product.quantity) + " " + product.unit));

    var actions = el("div", "actions");
    var deltaInput = el("input", "qty-input");
    deltaInput.type = "number";
    deltaInput.step = "0.001";
    deltaInput.value = "1";
    deltaInput.min = "0";
    deltaInput.setAttribute("aria-label", "Ajuste de cantidad de " + product.name + " en " + product.unit);
    actions.appendChild(deltaInput);

    var minus = el("button", "secondary", "−");
    minus.type = "button";
    minus.title = "Restar";
    minus.setAttribute("aria-label", "Restar existencias de " + product.name);
    minus.addEventListener("click", function () { adjust(product.id, deltaInput.value, -1); });
    actions.appendChild(minus);

    var plus = el("button", "secondary", "+");
    plus.type = "button";
    plus.title = "Sumar";
    plus.setAttribute("aria-label", "Sumar existencias de " + product.name);
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
    var version = refreshVersion;
    return api("/api/products").then(function (products) {
      if (version !== refreshVersion) return;
      productsCache = products;
      var stats = stockSummary(products);
      setMetric("m-zero", stats.zero);
      document.getElementById("stock-summary").textContent = stats.total ? (stats.total - stats.zero) + " de " + stats.total + " referencias tienen cantidad mayor que cero. No se aplica un umbral de stock." : "Sin productos registrados. No hay cobertura que calcular.";
      filterProducts();
    });
  }

  function filterProducts() {
    var zeroOnly = document.getElementById("product-filter").value === "zero";
    var products = productsCache.filter(function (p) { return !zeroOnly || Number(p.quantity) === 0; });
    var list = document.getElementById("product-list");
    replaceList(list, products, renderProduct);
    var empty = document.getElementById("products-empty");
    empty.hidden = products.length !== 0;
    empty.textContent = zeroOnly ? "No hay productos con cantidad cero." : "No hay productos.";
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
    labelInput(main, nameInput, "Nombre");
    labelInput(main, catInput, "Categoría (opcional)");
    labelInput(main, unitInput, "Unidad");
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
    cancel.addEventListener("click", filterProducts);
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
    var select = el("button", "secondary", "Ver en maqueta");
    select.type = "button";
    select.dataset.locationSelect = loc.id;
    select.setAttribute("aria-pressed", "false");
    select.addEventListener("click", function () { if (window.OpleCity) window.OpleCity.select(loc.id); });
    actions.appendChild(select);
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
    var version = ++locationLoadVersion;
    return api("/api/locations").then(function (locations) {
      if (version !== locationLoadVersion) return;
      var list = document.getElementById("location-list");
      replaceList(list, locations, renderLocation);
      if (window.OpleCity) window.OpleCity.render(locations);
      document.getElementById("locations-empty").hidden = locations.length !== 0;
    });
  }
  var locationLoadVersion = 0;

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
    xInput.required = true;
    xInput.value = loc.pos_x;
    var yInput = el("input");
    yInput.type = "number";
    yInput.min = "0";
    yInput.max = "1";
    yInput.step = "0.01";
    yInput.required = true;
    yInput.value = loc.pos_y;
    labelInput(main, nameInput, "Nombre");
    labelInput(main, addressInput, "Dirección");
    labelInput(main, xInput, "Posición x (0–1)");
    labelInput(main, yInput, "Posición y (0–1)");
    var demoInput = el("input");
    demoInput.type = "checkbox";
    demoInput.checked = loc.is_demo;
    labelInput(main, demoInput, "Datos ficticios de demostración");
    li.appendChild(main);

    var actions = el("div", "actions");
    var save = el("button", "", "Guardar");
    save.type = "button";
    save.addEventListener("click", function () {
      var name = nameInput.value.trim();
      var address = addressInput.value.trim();
      var rawX = xInput.value.trim();
      var rawY = yInput.value.trim();
      if (!rawX || !rawY) {
        toast("Ambas posiciones normalizadas son obligatorias.", true);
        return;
      }
      var x = Number(rawX);
      var y = Number(rawY);
      if (!name) { toast("El nombre es obligatorio.", true); return; }
      if (!address) { toast("La dirección es obligatoria.", true); return; }
      if (!isFinite(x) || x < 0 || x > 1 || !isFinite(y) || y < 0 || y > 1) {
        toast("La posición normalizada debe estar entre 0 y 1.", true);
        return;
      }
      api("/api/locations/" + loc.id, {
        method: "PATCH",
        body: { name: name, address: address, pos_x: x, pos_y: y, is_demo: demoInput.checked }
      }).then(refresh).catch(function (err) { toast(err.message, true); });
    });
    var cancel = el("button", "secondary", "Cancelar");
    cancel.type = "button";
    cancel.addEventListener("click", function () { loadLocations().catch(function (err) { toast(err.message, true); }); });
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
    document.getElementById("task-filter").addEventListener("change", function () { loadTasks().catch(function (err) { toast(err.message, true); }); });
    document.getElementById("product-filter").addEventListener("change", filterProducts);
    document.getElementById("refresh-btn").addEventListener("click", refresh);
    var links = document.querySelectorAll(".sidebar nav a");
    function activate(hash) {
      links.forEach(function (link) {
        if (link.getAttribute("href") === hash) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      });
    }
    links.forEach(function (link) { link.addEventListener("click", function () { activate(link.getAttribute("href")); }); });
    window.addEventListener("hashchange", function () { activate(window.location.hash || "#resumen"); });
    activate(window.location.hash || "#resumen");
    if (typeof IntersectionObserver !== "undefined") {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) { if (entry.isIntersecting) activate("#" + entry.target.id); });
      }, { rootMargin: "-10% 0px -65% 0px", threshold: 0 });
      document.querySelectorAll(".admin-layout > section").forEach(function (section) { observer.observe(section); });
    }

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

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootstrap);
    else bootstrap();
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { stockSummary: stockSummary, taskDistribution: taskDistribution, formatCreated: formatCreated };
})();
