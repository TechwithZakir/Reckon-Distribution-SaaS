frappe.pages["field-sales"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Field Sales"), single_column: true });
  let selected = null;
  const queueKey = "reckon_distribution_sync_queue";

  $(page.body).html(`
    <main class="rd-field-sales">
      <section class="rd-field-sales__top"><div><p class="rd-kicker">${__("আজকের রুট")}</p><h2>${__("Field Sales")}</h2></div><span class="rd-sync-state" data-sync-state>${__("Ready to sync")}</span></section>
      <label class="rd-search"><span>${__("Search retailer")}</span><input data-retailer-search placeholder="${__("Retailer name")}" /></label>
      <section class="rd-outlets" data-outlets><p class="text-muted">${__("Loading assigned outlets...")}</p></section>
      <section class="rd-retailer-panel" data-retailer-panel hidden>
        <div class="rd-balance-strip"><span>${__("Current due")}</span><strong data-net-due>৳0</strong></div>
        <div class="rd-field-actions"><button class="btn btn-primary" data-start-visit>${__("Start visit")}</button><button class="btn btn-default" data-new-order>${__("New order")}</button></div>
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
  $(page.body).find("[data-new-order]").on("click", () => frappe.set_route("sr-order", "new-sr-order"));

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
    frappe.call({ method: "reckon_distribution.field_sales.get_retailer_summary", args: { customer, route: selected.route } }).then((r) => {
      $(page.body).find("[data-net-due]").text(formatMoney(r.message.net_due));
      $(page.body).find("[data-message]").text(__("Delivery and collection remain available from this retailer screen."));
    });
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
