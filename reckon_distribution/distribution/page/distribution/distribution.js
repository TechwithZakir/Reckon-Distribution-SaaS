frappe.pages["distribution"].on_page_load = function (wrapper) {
  frappe.require("/assets/reckon_distribution/css/distribution_dashboard.css");
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Distribution Dashboard"),
    single_column: true,
  });
  page.set_primary_action(__("Refresh"), () => loadDashboard());

  $(page.body).html(`
    <main class="reckon-distribution-desk rd-dashboard-page">
      <header class="rd-dashboard-heading">
        <div>
          <p class="rd-kicker">${__("Reckon Distribution")}</p>
          <h1>${__("Distribution Dashboard")}</h1>
          <p data-company>${__("Loading company dashboard...")}</p>
        </div>
        <div class="rd-dashboard-period">
          <label>${__("From")}</label><input type="date" data-from-date />
          <label>${__("To")}</label><input type="date" data-to-date />
          <button class="btn btn-primary" data-refresh>${__("Refresh")}</button>
        </div>
      </header>

      <section class="rd-dashboard-kpis" data-kpis></section>
      <section class="rd-dashboard-grid rd-dashboard-grid--trend">
        <section class="rd-panel rd-panel--wide"><div class="rd-section-heading"><div><h2>${__("Sales, Delivery & Purchase Trend")}</h2><p>${__("Operational value across the selected period.")}</p></div><span class="rd-legend"><i class="sales"></i>${__("Sales")} <i class="purchase"></i>${__("Purchase")} <i class="expense"></i>${__("Expense")} <i class="collection"></i>${__("Collection")}</span></div><div data-trend></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><div><h2>${__("Profit & Loss")}</h2><p>${__("Delivered sales less purchases and expenses.")}</p></div></div><div data-profit></div></section>
      </section>
      <section class="rd-dashboard-grid">
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("SR / DSR Performance")}</h2></div><div data-performance></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Top Customers")}</h2><button class="btn btn-link btn-xs" data-list="Customer">${__("View All")}</button></div><div data-customers></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Delivery Status")}</h2></div><div data-delivery-status></div></section>
      </section>
      <section class="rd-dashboard-grid">
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Receivables Aging")}</h2></div><div data-receivables-aging></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Payables Aging")}</h2></div><div data-payables-aging></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Top Suppliers")}</h2><button class="btn btn-link btn-xs" data-list="Supplier">${__("View All")}</button></div><div data-suppliers></div></section>
      </section>
      <section class="rd-dashboard-grid">
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Sales Order Status")}</h2></div><div data-order-status></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Purchase Receipt Status")}</h2></div><div data-purchase-status></div></section>
        <section class="rd-panel"><div class="rd-section-heading"><h2>${__("Collection Status")}</h2></div><div data-collection-status></div></section>
      </section>
      <section class="rd-panel rd-panel--table"><div class="rd-section-heading"><div><h2>${__("Recent Distribution Activity")}</h2><p>${__("Deliveries, collections, purchases and expenses in the selected period.")}</p></div></div><div data-activity></div></section>
      <section class="rd-dashboard-grid rd-dashboard-grid--actions"><section class="rd-panel"><div class="rd-section-heading"><h2>${__("Quick Actions")}</h2></div><div class="rd-dashboard-actions" data-actions></div></section><section class="rd-panel rd-dashboard-note"><h2>${__("Analytics Scope")}</h2><p>${__("All figures are limited to the active tenant company and the selected date range. Values respect normal Frappe permissions.")}</p></section></section>
    </main>
  `);

  $(page.body).find("[data-refresh]").on("click", () => loadDashboard());
  $(page.body).on("click", "[data-list]", function () {
    frappe.set_route("List", $(this).data("list"));
  });
  loadDashboard();

  const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
  const money = (value, currency) => new Intl.NumberFormat(undefined, {
    style: "currency", currency: currency || "BDT", maximumFractionDigits: 0,
  }).format(Number(value || 0));
  const number = (value) => new Intl.NumberFormat(undefined, {maximumFractionDigits: 0}).format(Number(value || 0));
  const width = (value, max) => `${Math.min(100, Math.max(0, Number(value || 0) / Math.max(1, max) * 100))}%`;

  function renderKpis(data) {
    const k = data.kpis || {};
    const currency = data.currency;
    const cards = [
      [__("Delivered Sales"), money(k.sales, currency), `${number(k.sales_count)} ${__("deliveries")}`, "blue"],
      [__("SR Orders"), number(k.orders), `${money(k.order_value, currency)} ${__("order value")}`, "purple"],
      [__("Purchases"), money(k.purchases, currency), `${number(k.purchase_count)} ${__("receipts")}`, "orange"],
      [__("Expenses"), money(k.expenses, currency), __("Submitted office expenses"), "red"],
      [k.profit < 0 ? __("Operating Loss") : __("Operating Profit"), money(Math.abs(k.profit), currency), k.profit < 0 ? __("Sales less purchases and expenses") : __("Contribution after costs"), k.profit < 0 ? "red" : "green"],
      [__("Collections"), money(k.collections, currency), __("Confirmed DSR receipts"), "teal"],
      [__("Receivables"), money(k.receivables, currency), __("Open customer invoices"), "yellow"],
      [__("Payables"), money(k.payables, currency), __("Open supplier invoices"), "violet"],
    ];
    $(page.body).find("[data-kpis]").html(cards.map((card) => `<article class="rd-kpi-card rd-kpi-card--${card[3]}"><span>${escape(card[0])}</span><strong>${escape(card[1])}</strong><small>${escape(card[2])}</small></article>`).join(""));
  }

  function renderTrend(rows, currency) {
    const max = Math.max(1, ...rows.flatMap((row) => [row.sales, row.purchases, row.expenses, row.collections]));
    $(page.body).find("[data-trend]").html(rows.length ? `<div class="rd-trend-chart">${rows.map((row) => `<div class="rd-trend-column"><div class="rd-bars"><i class="sales" style="height:${width(row.sales, max)}" title="${escape(money(row.sales, currency))}"></i><i class="purchase" style="height:${width(row.purchases, max)}" title="${escape(money(row.purchases, currency))}"></i><i class="expense" style="height:${width(row.expenses, max)}" title="${escape(money(row.expenses, currency))}"></i><i class="collection" style="height:${width(row.collections, max)}" title="${escape(money(row.collections, currency))}"></i></div><small>${escape(row.label)}</small></div>`).join("")}</div>` : `<p class="text-muted">${__("No operational data in this period.")}</p>`);
  }

  function renderProfit(rows, currency) {
    const max = Math.max(1, ...rows.map((row) => Math.abs(Number(row.profit || 0))));
    $(page.body).find("[data-profit]").html(rows.length ? `<div class="rd-profit-list">${rows.map((row) => `<div><span>${escape(row.label)}</span><i><em class="${row.profit < 0 ? "loss" : "profit"}" style="width:${width(Math.abs(row.profit), max)}"></em></i><b class="${row.profit < 0 ? "loss-text" : "profit-text"}">${escape(money(row.profit, currency))}</b></div>`).join("")}</div>` : `<p class="text-muted">${__("No profit or loss data in this period.")}</p>`);
  }

  function renderRanked(selector, rows, currency, empty) {
    const max = Math.max(1, ...rows.map((row) => Number(row.amount || 0)));
    $(page.body).find(selector).html(rows.length ? `<div class="rd-ranking">${rows.map((row) => `<div><span>${escape(row.name)}</span><b>${escape(money(row.amount, currency))}</b><i><em style="width:${width(row.amount, max)}"></em></i></div>`).join("")}</div>` : `<p class="text-muted">${escape(empty)}</p>`);
  }

  function renderPerformance(rows, currency) {
    const max = Math.max(1, ...rows.map((row) => Number(row.amount || 0)));
    $(page.body).find("[data-performance]").html(rows.length ? `<div class="rd-performance-list">${rows.map((row) => `<div><span><strong>${escape(row.name)}</strong><small>${escape(row.role)} · ${number(row.count)} ${__("activities")}</small></span><b>${escape(money(row.amount, currency))}</b><i><em style="width:${width(row.amount, max)}"></em></i></div>`).join("")}</div>` : `<p class="text-muted">${__("No SR or DSR activity in this period.")}</p>`);
  }

  function renderStatus(selector, rows) {
    const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0);
    $(page.body).find(selector).html(rows.length ? `<div class="rd-status-list">${rows.map((row) => `<div><span>${escape(row.label)}</span><b>${number(row.count)}</b><small>${total ? Math.round(row.count / total * 100) : 0}%</small></div>`).join("")}</div>` : `<p class="text-muted">${__("No records in this period.")}</p>`);
  }

  function renderAging(selector, rows, currency, tone) {
    const total = rows.reduce((sum, row) => sum + Number(row.amount || 0), 0);
    let offset = 0;
    const colors = ["#25b878", "#f4a62a", "#ed7d4f", "#e45c68"];
    const stops = rows.map((row, index) => { const start = offset; offset += total ? row.amount / total * 100 : 0; return `${colors[index]} ${start}% ${offset}%`; }).join(", ");
    $(page.body).find(selector).html(`<div class="rd-aging"><div class="rd-donut ${tone}" style="background:conic-gradient(${stops || "#e8eef5 0 100%"})"><div><strong>${escape(money(total, currency))}</strong><small>${__("Total")}</small></div></div><div class="rd-aging-list">${rows.map((row, index) => `<div><span><i style="background:${colors[index]}"></i>${escape(row.label)}</span><b>${escape(money(row.amount, currency))}</b><small>${number(row.percentage)}%</small></div>`).join("")}</div></div>`);
  }

  function renderActivity(rows, currency) {
    const html = rows.length ? `<div class="rd-table-wrap"><table><thead><tr><th>${__("Date")}</th><th>${__("Activity")}</th><th>${__("Status")}</th><th>${__("Amount")}</th></tr></thead><tbody>${rows.map((row) => `<tr data-doctype="${escape(row.doctype)}" data-name="${escape(row.name)}"><td>${escape(row.date)}</td><td><strong>${escape(row.label)}</strong><small>${escape(row.name)}</small></td><td><span class="rd-status">${escape(row.status)}</span></td><td>${escape(money(row.amount, currency))}</td></tr>`).join("")}</tbody></table></div>` : `<p class="text-muted">${__("No recent activity in this period.")}</p>`;
    $(page.body).find("[data-activity]").html(html).find("tr[data-doctype]").on("click", function () { frappe.set_route("Form", $(this).data("doctype"), $(this).data("name")); });
  }

  function renderActions(management) {
    const actions = [
      [__("New SR Order"), "SR Order", "field-sales"],
      [__("New Delivery Note"), "Delivery Note", "dsr-delivery"],
      [__("New DSR Collection"), "DSR Collection Receipt", "dsr-delivery"],
      [__("New Outlet Visit"), "Outlet Visit", "field-sales"],
    ];
    if (management) actions.push([__("New Purchase Receipt"), "Purchase Receipt", "List"]);
    $(page.body).find("[data-actions]").html(actions.map((action) => `<button class="rd-dashboard-action" data-doctype="${escape(action[1])}"><strong>${escape(action[0])}</strong><span>${escape(action[2])}</span></button>`).join("")).find("[data-doctype]").on("click", function () { frappe.new_doc($(this).data("doctype")); });
  }

  function renderDashboard(data) {
    $(page.body).find("[data-company]").text(__("Operational overview for {0}.", [data.company || ""]));
    $(page.body).find("[data-from-date]").val(data.from_date || "");
    $(page.body).find("[data-to-date]").val(data.to_date || "");
    renderKpis(data);
    renderTrend(data.trend || [], data.currency);
    renderProfit(data.trend || [], data.currency);
    renderPerformance(data.performance || [], data.currency);
    renderRanked("[data-customers]", data.top_customers || [], data.currency, __("No delivered sales found."));
    renderRanked("[data-suppliers]", data.top_suppliers || [], data.currency, __("No purchase receipts found."));
    renderStatus("[data-delivery-status]", data.delivery_status || []);
    renderStatus("[data-order-status]", data.order_status || []);
    renderStatus("[data-purchase-status]", data.purchase_status || []);
    renderStatus("[data-collection-status]", data.collection_status || []);
    renderAging("[data-receivables-aging]", data.receivables_aging || [], data.currency, "receivable");
    renderAging("[data-payables-aging]", data.payables_aging || [], data.currency, "payable");
    renderActivity(data.recent_activity || [], data.currency);
    renderActions(Boolean(data.management));
  }

  function loadDashboard() {
    const args = {from_date: $(page.body).find("[data-from-date]").val(), to_date: $(page.body).find("[data-to-date]").val()};
    $(page.body).find("[data-company]").text(__("Loading company dashboard..."));
    frappe.call({method: "reckon_distribution.dashboard.get_distribution_dashboard", args, freeze: false}).then((response) => renderDashboard(response.message || {})).catch((error) => {
      console.error("Distribution Dashboard failed", error);
      $(page.body).find("[data-company]").text(__("Dashboard data is unavailable right now."));
      $(page.body).find("[data-kpis]").html(`<div class="rd-dashboard-error"><strong>${__("Unable to load distribution analytics")}</strong><span>${escape(error?.message || __("Check the server log for details."))}</span></div>`);
    });
  }
};
