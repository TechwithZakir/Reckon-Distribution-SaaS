frappe.pages["distribution-master-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Master Setup"),
    single_column: true,
  });

  $(page.body).html(`
    <div class="rd-master-setup">
      <section class="rd-master-hero">
        <div>
          <p class="rd-kicker">${__("Distribution control")}</p>
          <h2>${__("Master data setup")}</h2>
          <p>${__("Configure the company catalogue and operating defaults before receiving supplier goods.")}</p>
        </div>
        <a class="btn btn-primary" href="/app/distribution">${__("Back to Distribution")}</a>
      </section>
      <div class="rd-master-notice">
        <strong>${__("Company-scoped access")}</strong>
        <span>${__("ERPNext Items, Suppliers, Customers, Prices, and Warehouses are shared references. Enable only the records assigned to this Company.")}</span>
      </div>
      <section class="rd-master-grid">
        ${master_card("Distribution Settings", "Company policy, supplier-goods rule, accounts, and defaults.", "distribution-settings")}
        ${master_card("Company UOM Profile", "Enable the shared ERPNext UOMs used by this Company.", "company-uom-profile")}
        ${master_card("Distribution Route", "Maintain SR/DSR route and territory assignments.", "distribution-route")}
        ${master_card("Distribution Master Scope", "Assign Items, Suppliers, Customers, Prices, and Warehouses.", "distribution-master-scope")}
        ${master_card("Item", "Open the ERPNext Item catalogue.", "item")}
        ${master_card("Supplier", "Open the ERPNext Supplier catalogue.", "supplier")}
        ${master_card("Customer", "Open the retailer Customer catalogue.", "customer")}
        ${master_card("Purchase Receipt", "Receive supplier-provided paid and free goods.", "purchase-receipt")}
      </section>
    </div>
  `);

  function master_card(title, description, route) {
    return `<a class="rd-master-card" href="/app/${route}"><span class="rd-master-card__icon">${title.charAt(0)}</span><span><strong>${__(title)}</strong><small>${__(description)}</small></span><span class="rd-master-card__arrow">&rarr;</span></a>`;
  }
};
