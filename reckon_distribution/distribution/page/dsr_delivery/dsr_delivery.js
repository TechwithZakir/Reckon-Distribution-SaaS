frappe.pages["dsr-delivery"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Deliver & Collect / ডেলিভারি ও টাকা সংগ্রহ"),
    single_column: true,
  });

  $(page.body).html(`
    <main class="rd-dsr-delivery">
      <header class="rd-dsr-hero">
        <div>
          <p class="rd-kicker">${__("DSR route work / DSR রুটের কাজ")}</p>
          <h2>${__("Deliver & Collect / ডেলিভারি ও টাকা সংগ্রহ")}</h2>
          <p>${__("Complete delivery and collection independently for each assigned retailer. / নির্ধারিত প্রতিটি রিটেইলারের ডেলিভারি ও টাকা আলাদাভাবে সম্পন্ন করুন।")}</p>
        </div>
        <span class="rd-sync-state" data-state>${__("Ready / প্রস্তুত")}</span>
      </header>
      <label class="rd-dsr-search">
        <span>${__("Search retailer / রিটেইলার খুঁজুন")}</span>
        <input data-search placeholder="${__("Retailer name / দোকানের নাম")}" />
      </label>
      <section class="rd-dsr-outlets" data-outlets><p class="text-muted">${__("Loading assigned retailers... / নির্ধারিত রিটেইলার লোড হচ্ছে...")}</p></section>
      <section class="rd-dsr-panel" data-panel hidden>
        <div class="rd-dsr-customer-head">
          <div><p class="text-muted">${__("Selected retailer / নির্বাচিত রিটেইলার")}</p><h3 data-customer></h3></div>
          <div class="rd-dsr-due"><span>${__("Current net due / বর্তমান বকেয়া")}</span><strong data-due>৳0</strong><small data-overdue></small></div>
        </div>
        <section class="rd-dsr-section">
          <h4>${__("1. Delivery / ১. ডেলিভারি")}</h4>
          <p class="text-muted">${__("Add only physically delivered stock. Supplier free goods need their submitted receipt source. / বাস্তবে দেওয়া পণ্যই যোগ করুন। সরবরাহকারীর ফ্রি পণ্যের জমা দেওয়া রসিদের উৎস দিন।")}</p>
          <div class="rd-dsr-fields">
            <label>${__("Van warehouse / ভ্যান গুদাম")}<input data-warehouse required /></label>
            <label>${__("Product / পণ্য")}<select data-item></select></label>
            <label>${__("Sales unit / বিক্রয় ইউনিট")}<select data-uom></select></label>
            <label>${__("Quantity / পরিমাণ")}<input data-qty type="number" min="0.001" step="0.001" /></label>
            <label>${__("Stock type / স্টকের ধরন")}<select data-category><option value="Saleable">${__("Saleable / বিক্রয়যোগ্য")}</option><option value="Supplier Free">${__("Supplier free / সরবরাহকারীর ফ্রি")}</option></select></label>
            <label>${__("Source receipt for free goods / ফ্রি পণ্যের উৎস রসিদ")}<input data-source placeholder="PR-00001" /></label>
          </div>
          <button class="btn btn-default" data-add-line>${__("Add delivery line / ডেলিভারি লাইন যোগ করুন")}</button>
          <div class="rd-dsr-lines" data-lines><p class="text-muted">${__("No delivery lines yet. / এখনও কোনো ডেলিভারি লাইন নেই।")}</p></div>
          <button class="btn btn-primary" data-submit-delivery>${__("Submit delivery / ডেলিভারি জমা দিন")}</button>
        </section>
        <section class="rd-dsr-section">
          <h4>${__("2. Collection / ২. টাকা সংগ্রহ")}</h4>
          <p class="text-muted">${__("Cash and cheque can confirm immediately. Bank and MFS remain pending until verified. / নগদ ও চেক সঙ্গে সঙ্গে নিশ্চিত হতে পারে। ব্যাংক ও MFS যাচাই না হওয়া পর্যন্ত অপেক্ষমাণ থাকবে।")}</p>
          <div class="rd-dsr-fields">
            <label>${__("Amount / পরিমাণ")}<input data-amount type="number" min="0.01" step="0.01" /></label>
            <label>${__("Method / মাধ্যম")}<select data-method><option>Cash</option><option>Cheque</option><option>Bank</option><option>MFS</option></select></label>
            <label>${__("Receiving account / গ্রহণের অ্যাকাউন্ট")}<input data-account required /></label>
            <label>${__("Reference / রেফারেন্স")}<input data-reference placeholder="${__("Required for Bank/MFS")}" /></label>
          </div>
          <button class="btn btn-primary" data-submit-collection>${__("Submit collection / টাকা জমা দিন")}</button>
        </section>
        <p class="rd-dsr-message" data-message></p>
      </section>
    </main>
  `);

  const body = $(page.body);
  const outlets = body.find("[data-outlets]");
  const panel = body.find("[data-panel]");
  const state = body.find("[data-state]");
  let assigned = [];
  let selected = null;
  let catalog = [];
  let lines = [];
  let deliveryKey = null;
  let collectionKey = null;

  loadOutlets();
  body.find("[data-search]").on("input", function () { renderOutlets(this.value); });
  body.find("[data-item]").on("change", renderUoms);
  body.find("[data-add-line]").on("click", addLine);
  body.find("[data-submit-delivery]").on("click", submitDelivery);
  body.find("[data-submit-collection]").on("click", submitCollection);

  function loadOutlets() {
    frappe.call({ method: "reckon_distribution.field_sales.get_assigned_outlets" }).then((response) => {
      assigned = response.message || [];
      renderOutlets();
      setState(__("Ready / প্রস্তুত"));
    }).catch(() => {
      setState(__("Offline: retry sync / অফলাইন: আবার চেষ্টা করুন"));
      outlets.html(`<p class="text-muted">${__("No network. / নেটওয়ার্ক নেই।")}</p>`);
    });
  }

  function renderOutlets(search = "") {
    const query = search.trim().toLowerCase();
    const rows = assigned.filter((row) => !query || row.customer.toLowerCase().includes(query));
    outlets.html(rows.length ? rows.map((row) => `<button class="rd-dsr-outlet" data-outlet="${esc(row.customer)}"><strong>${esc(row.customer)}</strong><small>${esc(row.route || "")}</small></button>`).join("") : `<p class="text-muted">${__("No assigned retailers found. / কোনো নির্ধারিত রিটেইলার নেই।")}</p>`);
    outlets.find("[data-outlet]").on("click", function () { selectRetailer($(this).data("outlet")); });
  }

  function selectRetailer(customer) {
    selected = assigned.find((row) => row.customer === customer);
    if (!selected) return;
    panel.prop("hidden", false);
    body.find("[data-customer]").text(customer);
    lines = [];
    deliveryKey = `delivery-${customer}-${Date.now()}`;
    collectionKey = `collection-${customer}-${Date.now()}`;
    renderLines();
    frappe.call({ method: "reckon_distribution.field_sales.get_retailer_summary", args: { customer, route: selected.route } }).then((response) => {
      const summary = response.message || {};
      body.find("[data-due]").text(formatMoney(summary.net_due));
      body.find("[data-overdue]").text(`${__("Overdue / মেয়াদোত্তীর্ণ")}: ${formatMoney(summary.overdue)}`);
    });
    frappe.call({ method: "reckon_distribution.field_sales.get_sales_catalog" }).then((response) => {
      catalog = response.message || [];
      renderCatalog();
    });
  }

  function renderCatalog() {
    const select = body.find("[data-item]");
    select.html(catalog.map((item) => `<option value="${esc(item.item_code)}">${esc(item.item_name || item.item_code)}</option>`).join(""));
    renderUoms();
  }

  function renderUoms() {
    const item = catalog.find((row) => row.item_code === body.find("[data-item]").val());
    const uoms = item ? [{ uom: item.stock_uom, conversion_factor: 1 }, ...(item.uoms || [])] : [];
    body.find("[data-uom]").html(uoms.map((row) => `<option value="${esc(row.uom)}">${esc(row.uom)} ×${row.conversion_factor}</option>`).join(""));
  }

  function addLine() {
    const item = catalog.find((row) => row.item_code === body.find("[data-item]").val());
    const qty = Number(body.find("[data-qty]").val());
    if (!item || !qty || qty <= 0) return showMessage(__("Choose a product and quantity first. / আগে পণ্য ও পরিমাণ নির্বাচন করুন।"), true);
    lines.push({ item_code: item.item_code, uom: body.find("[data-uom]").val() || item.stock_uom, qty, rd_stock_category: body.find("[data-category]").val(), rd_supplier_free_source: body.find("[data-source]").val() });
    body.find("[data-qty], [data-source]").val("");
    renderLines();
  }

  function renderLines() {
    const target = body.find("[data-lines]");
    target.html(lines.length ? lines.map((line, index) => `<div class="rd-dsr-line"><span>${esc(line.item_code)} · ${esc(line.uom)} × ${line.qty}</span><small>${esc(line.rd_stock_category)}</small><button class="btn btn-xs btn-default" data-remove-line="${index}">${__("Remove")}</button></div>`).join("") : `<p class="text-muted">${__("No delivery lines yet. / এখনও কোনো ডেলিভারি লাইন নেই।")}</p>`);
    target.find("[data-remove-line]").on("click", function () { lines.splice(Number($(this).data("remove-line")), 1); renderLines(); });
  }

  function submitDelivery() {
    if (!selected || !lines.length) return showMessage(__("Select a retailer and add delivery lines. / রিটেইলার নির্বাচন করে ডেলিভারি লাইন যোগ করুন।"), true);
    const payload = { customer: selected.customer, route: selected.route, warehouse: body.find("[data-warehouse]").val(), items: lines, idempotency_key: deliveryKey };
    withGps((gps) => {
      Object.assign(payload, gps);
      frappe.call({ method: "reckon_distribution.field_sales.submit_distribution_delivery", args: { payload: JSON.stringify(payload) } }).then((response) => {
        showMessage(__("Delivery saved: {0} / ডেলিভারি সংরক্ষিত: {0}", [response.message]));
        lines = [];
        deliveryKey = `delivery-${selected.customer}-${Date.now()}`;
        renderLines();
      }).catch(() => showMessage(__("Delivery could not be saved. / ডেলিভারি সংরক্ষণ করা যায়নি।"), true));
    });
  }

  function submitCollection() {
    if (!selected) return showMessage(__("Select a retailer first. / আগে রিটেইলার নির্বাচন করুন।"), true);
    const payload = { customer: selected.customer, route: selected.route, amount: Number(body.find("[data-amount]").val()), payment_method: body.find("[data-method]").val(), receiving_account: body.find("[data-account]").val(), reference_no: body.find("[data-reference]").val(), idempotency_key: collectionKey };
    withGps((gps) => {
      Object.assign(payload, gps);
      frappe.call({ method: "reckon_distribution.collection.record_collection", args: { payload: JSON.stringify(payload) } }).then((response) => {
        showMessage(__("Collection saved: {0} / টাকা সংগ্রহ সংরক্ষিত: {0}", [response.message]));
        collectionKey = `collection-${selected.customer}-${Date.now()}`;
        body.find("[data-amount], [data-reference]").val("");
      }).catch(() => showMessage(__("Collection could not be saved. / টাকা সংগ্রহ সংরক্ষণ করা যায়নি।"), true));
    });
  }

  function withGps(done) {
    if (!navigator.geolocation) return done({});
    navigator.geolocation.getCurrentPosition((position) => done({ gps_latitude: position.coords.latitude, gps_longitude: position.coords.longitude, gps_accuracy: position.coords.accuracy }), () => done({}));
  }

  function showMessage(message, error = false) { body.find("[data-message]").text(message).toggleClass("text-danger", error); }
  function setState(value) { state.text(value); }
  function formatMoney(value) { return `৳${Number(value || 0).toFixed(2)}`; }
  function esc(value) { return frappe.utils.escape_html(String(value || "")); }
};
