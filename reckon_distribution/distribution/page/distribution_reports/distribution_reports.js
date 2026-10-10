frappe.pages["distribution-reports"].on_page_load = function (wrapper) {
  frappe.require("/assets/reckon_distribution/css/distribution_pages.css");
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Distribution Reports"),
    single_column: true,
  });
  page.set_primary_action(__("Refresh"), () => loadReports());

  $(page.body).html(`
    <main class="rd-reports rd-theme-page">
      <header class="rd-page-heading">
        <p class="rd-kicker">${__("Reporting")}</p>
        <h2>${__("Distribution Reports")}</h2>
        <p>${__("Open the current company's stock, sales, and procurement reports.")}</p>
      </header>
      <section class="rd-report-grid" data-reports>
        <p class="text-muted">${__("Loading reports...")}</p>
      </section>
    </main>
  `);

  loadReports();

  function loadReports() {
    frappe.call({ method: "reckon_distribution.dashboard.get_distribution_report_catalog" })
      .then((response) => renderReports(response.message || []))
      .catch(() => $(page.body).find("[data-reports]").html(`<p class="text-muted">${__("Reports are unavailable right now.")}</p>`));
  }

  function renderReports(reports) {
    const container = $(page.body).find("[data-reports]");
    container.html(reports.length ? reports.map((report) => `
      <button class="rd-report-card" data-route="${frappe.utils.escape_html(report.route)}" data-route-type="${report.route_type}">
        <strong>${frappe.utils.escape_html(report.label)}</strong>
        <span>${frappe.utils.escape_html(report.description)}</span>
      </button>
    `).join("") : `<p class="text-muted">${__("No reports are available for your role.")}</p>`);
    container.find("[data-route]").on("click", function () {
      const route = $(this).data("route");
      if ($(this).data("route-type") === "report") {
        frappe.set_route("query-report", route);
      } else {
        frappe.set_route("List", "Stock Ledger Entry");
      }
    });
  }
};
