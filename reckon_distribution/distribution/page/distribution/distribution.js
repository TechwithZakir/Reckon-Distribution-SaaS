frappe.pages["distribution"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Distribution"),
    single_column: true,
  });

  $(page.body).html(`
    <div class="reckon-distribution-page">
      <div class="frappe-card">
        <h3>${__("Distribution Workspace")}</h3>
        <p class="text-muted">
          ${__(
            "Foundation shell only. Tenant security and operational workflows will be added in later phases."
          )}
        </p>
      </div>
    </div>
  `);
};
