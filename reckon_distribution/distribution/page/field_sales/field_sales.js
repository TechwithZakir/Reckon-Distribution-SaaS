frappe.pages["field-sales"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Field Sales"), single_column: true });
  let selected = null;
  let catalog = [];
  let orderItems = [];
  const queueKey = "reckon_distribution_sync_queue";

  $(page.body).html(`
    <main class="rd-field-sales">
      <section class="rd-field-sales__top"><div><p class="rd-kicker">${__("আজকের রুট")}</p><h2>${__("Field Sales")}</h2></div><span class="rd-sync-state" data-sync-state>${__("Ready to sync")}</span></section>
      <label class="rd-search"><span>${__("Search retailer")}</span><input data-retailer-search placeholder="${__("Retailer name")}" /></label>
      <section class="rd-outlets" data-outlets><p class="text-muted">${__("Loading assigned outlets...")}</p></section>
      <section class="rd-retailer-panel" data-retailer-panel hidden>
        <div class="rd-balance-strip"><span>${__("Current due")}</span><strong data-net-due>৳0</strong></div>
        <div class="rd-field-actions"><button class="btn btn-primary" data-start-visit>${__("Start visit")}</button></div>
        <section class="rd-order-composer"><h4>${__("Order draft")}</h4><div class="rd-order-row"><select data-item></select><select data-uom></select><input data-qty type="number" min="0.001" step="0.001" placeholder="${__("Qty")}" /><button class="btn btn-default" data-add-item>${__("Add")}</button></div><div data-order-items></div><button class="btn btn-primary" data-save-order>${__("Save order draft")}</button><div class="rd-delivery-row"><input data-warehouse placeholder="${__("Van warehouse")}" /><button class="btn btn-default" data-submit-delivery>${__("Save delivery")}</button></div></section>
        <p class="text-muted" data-message>${__("Select an outlet to see its balance.")}</p>
      </section>
    </main>
  `);

  const outlets = $(page.body).find("[data-outlets]");
  const panel = $(page.body).find("[data-retailer-panel]");
  const state = $(page.body).find("[data-sync-state]");
  let assigned = [];

  loadOutlets();
  syncQueue();
  $(page.body).find("[data-retailer-search]").on("input", function () { renderOutlets(this.value); });
  $(page.body).find("[data-start-visit]").on("click", () => saveVisit());
  $(page.body).find("[data-add-item]").on("click", addItem);
  $(page.body).find("[data-save-order]").on("click", saveOrder);
  $(page.body).find("[data-submit-delivery]").on("click", submitDelivery);
  $(page.body).find("[data-item]").on("change", renderUoms);

  function loadOutlets() {
    frappe.call({ method: "reckon_distribution.field_sales.get_assigned_outlets" }).then((r) => {
      assigned = r.message || [];
      renderOutlets();
    }).catch(() => { setState(__("Offline: retry sync")); outlets.html(`<p class="text-muted">${__("No network. Saved work stays on this device.")}</p>`); });
  }

  function renderOutlets(txt = "") {
    const rows = assigned.filter((row) => !txt || row.customer.toLowerCase().includes(txt.toLowerCase()));
    outlets.html(rows.length ? rows.map((row) => `<button class="rd-outlet-row" data-outlet="${frappe.utils.escape_html(row.customer)}"><strong>${frappe.utils.escape_html(row.customer)}</strong><small>${frappe.utils.escape_html(row.route || "")}</small></button>`).join("") : `<p class="text-muted">${__("No assigned retailers found.")}</p>`);
    outlets.find("[data-outlet]").on("click", function () { selectRetailer($(this).data("outlet")); });
  }

  function selectRetailer(customer) {
    selected = assigned.find((row) => row.customer === customer);
    panel.prop("hidden", false);
    orderItems = [];
    loadCatalog();
    frappe.call({ method: "reckon_distribution.field_sales.get_retailer_summary", args: { customer, route: selected.route } }).then((r) => {
      $(page.body).find("[data-net-due]").text(formatMoney(r.message.net_due));
      $(page.body).find("[data-message]").text(__("Delivery and collection remain available from this retailer screen."));
    });
  }

  function loadCatalog() {
    frappe.call({ method: "reckon_distribution.field_sales.get_sales_catalog" }).then((r) => { catalog = r.message || []; renderCatalog(); });
  }

  function renderCatalog() {
    const select = $(page.body).find("[data-item]");
    select.html(catalog.map((item) => `<option value="${frappe.utils.escape_html(item.item_code)}">${frappe.utils.escape_html(item.item_name || item.item_code)}</option>`).join(""));
    renderUoms();
  }

  function renderUoms() {
    const item = catalog.find((row) => row.item_code === $(page.body).find("[data-item]").val());
    const uoms = item ? [{ uom: item.stock_uom, conversion_factor: 1 }, ...(item.uoms || [])] : [];
    $(page.body).find("[data-uom]").html(uoms.map((uom) => `<option value="${frappe.utils.escape_html(uom.uom)}">${frappe.utils.escape_html(uom.uom)} x${uom.conversion_factor}</option>`).join(""));
  }

  function addItem() {
    const item = catalog.find((row) => row.item_code === $(page.body).find("[data-item]").val());
    const qty = Number($(page.body).find("[data-qty]").val());
    if (!item || !qty || qty <= 0) return frappe.msgprint(__("Select an item and enter a quantity."));
    orderItems.push({ item_code: item.item_code, uom: $(page.body).find("[data-uom]").val(), qty });
    $(page.body).find("[data-order-items]").html(orderItems.map((row) => `<div class="rd-order-line"><span>${frappe.utils.escape_html(row.item_code)} / ${frappe.utils.escape_html(row.uom)}</span><strong>${row.qty}</strong></div>`).join(""));
    $(page.body).find("[data-qty]").val("");
  }

  function saveOrder() {
    if (!selected || !orderItems.length) return frappe.msgprint(__("Add at least one item."));
    const payload = { customer: selected.customer, route: selected.route, price_list: catalog[0] && catalog[0].price_list, idempotency_key: `order-${selected.customer}-${Date.now()}`, items: orderItems };
    frappe.call({ method: "reckon_distribution.field_sales.save_sr_order", args: { payload: JSON.stringify(payload) } }).then((r) => { setState(__("Order draft saved: {0}", [r.message])); orderItems = []; }).catch(() => queue(payload, "order"));
  }

  function submitDelivery() {
    if (!selected || !orderItems.length) return frappe.msgprint(__("Add at least one item."));
    const warehouse = $(page.body).find("[data-warehouse]").val();
    if (!warehouse) return frappe.msgprint(__("Enter the van warehouse."));
    const payload = { customer: selected.customer, route: selected.route, warehouse, price_list: catalog[0] && catalog[0].price_list, idempotency_key: `delivery-${selected.customer}-${Date.now()}`, items: orderItems };
    frappe.call({ method: "reckon_distribution.field_sales.submit_distribution_delivery", args: { payload: JSON.stringify(payload) } }).then((r) => { setState(__("Delivery submitted: {0}", [r.message])); orderItems = []; }).catch(() => queue(payload, "delivery"));
  }

  function saveVisit() {
    if (!selected) return;
    const key = `visit-${selected.customer}-${Date.now()}`;
    const payload = { customer: selected.customer, route: selected.route, idempotency_key: key, visit_status: "Started" };
    frappe.call({ method: "reckon_distribution.field_sales.record_outlet_visit", args: { payload: JSON.stringify(payload) } }).then(() => setState(__("Visit saved"))).catch(() => queue(payload, "visit"));
  }

  function queue(payload, type) {
    const queue = JSON.parse(localStorage.getItem(queueKey) || "[]");
    queue.push({ type, payload, queued_at: new Date().toISOString() });
    localStorage.setItem(queueKey, JSON.stringify(queue));
    setState(__("Saved offline: waiting to sync"));
  }

  function syncQueue() {
    const queue = JSON.parse(localStorage.getItem(queueKey) || "[]");
    if (!queue.length) return;
    frappe.call({ method: "reckon_distribution.field_sales.sync_field_sales_queue", args: { events: JSON.stringify(queue) } }).then(() => {
      localStorage.removeItem(queueKey);
      setState(__("Offline work synced"));
    }).catch(() => setState(__("Offline: waiting to sync")));
  }

  function setState(label) { state.text(label); }
  function formatMoney(value) { return `৳${Number(value || 0).toLocaleString()}`; }
};
