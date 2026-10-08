frappe.pages["distribution"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Distribution"),
    single_column: true,
  });

  page.set_primary_action(__("Refresh"), function () {
    frappe.set_route("distribution");
  });

  $(page.body).html(`
    <div class="reckon-distribution-desk">
      <section class="rd-desk-hero">
        <p class="rd-kicker">${__("Reckon Distribution")}</p>
        <h2>${__("Distribution Workspace")}</h2>
        <p>${__(
          "Bangla-first SR/DSR distribution shell for company-isolated FMCG operations."
        )}</p>
      </section>
      <section class="rd-desk-grid">
        <a class="rd-desk-card" href="/desk/van-loading">
          <h3>${__("Van Loading")}</h3>
          <p>${__("Manager challans, Stock Entry custody, and DSR acknowledgement.")}</p>
        </a>
        <a class="rd-desk-card" href="/desk/distribution-master-setup">
          <h3>${__("Master Setup")}</h3>
          <p>${__("Company-scoped Items, suppliers, customers, prices, UOM, and routes.")}</p>
        </a>
        <a class="rd-desk-card" href="/reckonerp-subscription">
          <h3>${__("Subscription")}</h3>
          <p>${__("Payment, activation, and provisioning status.")}</p>
        </a>
        <a class="rd-desk-card" href="/distribution">
          <h3>${__("Web Shell")}</h3>
          <p>${__("Open the public-facing distribution landing shell.")}</p>
        </a>
      </section>
    </div>
  `);
};
