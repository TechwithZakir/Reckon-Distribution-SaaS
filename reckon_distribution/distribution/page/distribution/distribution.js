frappe.pages["distribution"].on_page_load = function (wrapper) {
  frappe.require("/assets/reckon_distribution/css/distribution_pages.css");
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Distribution Home"),
    single_column: true,
  });
  page.set_primary_action(__("Refresh"), () => loadDashboard());

  $(page.body).html(`
    <main class="reckon-distribution-desk rd-theme-page">
      <header class="rd-dashboard-heading">
        <div>
          <p class="rd-kicker">${__("Reckon Distribution")}</p>
          <h2>${__("Distribution Home")}</h2>
          <p data-company>${__("Loading company dashboard...")}</p>
        </div>
        <div class="rd-dashboard-period">
          <label>${__("From")}<input type="date" data-from-date /></label>
          <label>${__("To")}<input type="date" data-to-date /></label>
          <button class="btn btn-default" data-refresh>${__("Refresh")}</button>
        </div>
      </header>

      <section class="rd-dashboard-kpis" data-kpis></section>

      <section class="rd-dashboard-section">
        <div class="rd-section-heading">
          <div><h3>${__("Today's work")}</h3><p>${__("Start a distribution workflow or review its native records.")}</p></div>
        </div>
        <div class="rd-dashboard-actions" data-actions></div>
      </section>

      <section class="rd-dashboard-section rd-dashboard-two-column">
        <div>
          <div class="rd-section-heading">
            <div><h3>${__("Recent activity")}</h3><p>${__("Submitted deliveries and confirmed DSR collections.")}</p></div>
          </div>
          <div class="rd-activity-list" data-activity></div>
        </div>
        <div>
          <div class="rd-section-heading">
            <div><h3>${__("Record lists")}</h3><p>${__("Open the history behind Field Sales and Delivery & Collection.")}</p></div>
          </div>
          <div class="rd-dashboard-lists" data-lists></div>
        </div>
      </section>
    </main>
  `);

  $(page.body).find("[data-refresh]").on("click", () => loadDashboard());
  loadDashboard();

  function loadDashboard() {
    const fromDate = $(page.body).find("[data-from-date]").val();
    const toDate = $(page.body).find("[data-to-date]").val();
    frappe.call({
      method: "reckon_distribution.dashboard.get_distribution_dashboard",
      args: { from_date: fromDate, to_date: toDate },
      freeze: false,
    }).then((response) => renderDashboard(response.message || {})).catch(() => {
      $(page.body).find("[data-company]").text(__("Dashboard data is unavailable right now."));
      $(page.body).find("[data-kpis]").html(`<p class="text-muted">${__("Unable to load the company dashboard.")}</p>`);
    });
  }

  function renderDashboard(data) {
    $(page.body).find("[data-company]").text(__("Operational overview for {0}.", [data.company || ""]));
    $(page.body).find("[data-from-date]").val(data.from_date || "");
    $(page.body).find("[data-to-date]").val(data.to_date || "");
    renderKpis(data.metrics || []);
    renderActions(Boolean(data.management));
    renderActivity(data.recent_activity || []);
    renderLists();
  }

  function renderKpis(metrics) {
    const colors = ["blue", "green", "orange", "purple", "teal", "red"];
    $(page.body).find("[data-kpis]").html(metrics.map((metric, index) => `
      <article class="rd-kpi-card rd-kpi-card--${colors[index % colors.length]}">
        <span>${frappe.utils.escape_html(metric.label)}</span>
        <strong>${metric.format === "currency" ? formatCurrency(metric.value) : frappe.utils.escape_html(String(metric.value || 0))}</strong>
        <small>${frappe.utils.escape_html(metric.detail)}</small>
      </article>
    `).join(""));
  }

  function renderActions(management) {
    const actions = [
      { label: __("DSR Challan"), detail: __("Load stock to a DSR van"), route: ["List", "DSR Challan"] },
      { label: __("Field Sales"), detail: __("Visits, order drafts, and route work"), route: ["field-sales"] },
      { label: __("Deliver & Collect"), detail: __("Submit delivery and collection"), route: ["dsr-delivery"] },
      { label: __("Stock Ledger"), detail: __("Review warehouse movement"), route: ["query-report", "Stock Ledger"] },
    ];
    if (management) {
      actions.splice(3, 0, { label: __("Purchase Received"), detail: __("Receive supplier goods"), route: ["List", "Purchase Receipt"] });
    }
    const container = $(page.body).find("[data-actions]");
    container.html(actions.map((action) => `
      <button class="rd-dashboard-action" data-route='${frappe.utils.escape_html(JSON.stringify(action.route))}'>
        <strong>${frappe.utils.escape_html(action.label)}</strong>
        <span>${frappe.utils.escape_html(action.detail)}</span>
      </button>
    `).join(""));
    container.find("[data-route]").on("click", function () {
      frappe.set_route(...JSON.parse($(this).attr("data-route")));
    });
  }

  function renderActivity(activity) {
    const container = $(page.body).find("[data-activity]");
    container.html(activity.length ? activity.map((row) => `
      <button class="rd-activity-row" data-doctype="${frappe.utils.escape_html(row.doctype)}" data-name="${frappe.utils.escape_html(row.name)}">
        <span><strong>${frappe.utils.escape_html(row.label)}</strong><small>${frappe.utils.escape_html(row.date)}</small></span>
        <strong>${row.format === "currency" ? formatCurrency(row.amount) : frappe.utils.escape_html(String(row.amount || ""))}</strong>
      </button>
    `).join("") : `<p class="text-muted">${__("No submitted activity in this period.")}</p>`);
    container.find("[data-doctype]").on("click", function () {
      frappe.set_route("Form", $(this).data("doctype"), $(this).data("name"));
    });
  }

  function renderLists() {
    const records = [
      { label: __("SR Orders"), doctype: "SR Order" },
      { label: __("Outlet Visits"), doctype: "Outlet Visit" },
      { label: __("Delivery Notes"), doctype: "Delivery Note" },
      { label: __("DSR Collections"), doctype: "DSR Collection Receipt" },
    ];
    const container = $(page.body).find("[data-lists]");
    container.html(records.map((record) => `
      <button class="rd-record-list-link" data-doctype="${record.doctype}">${frappe.utils.escape_html(record.label)}</button>
    `).join(""));
    container.find("[data-doctype]").on("click", function () {
      frappe.set_route("List", $(this).data("doctype"));
    });
  }

  function formatCurrency(value) {
    return frappe.format(value || 0, { fieldtype: "Currency" });
  }
};
