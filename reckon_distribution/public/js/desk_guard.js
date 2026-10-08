(function () {
  const allowedRoutes = new Set([
    "distribution",
    "distribution-master-setup",
    "distribution-team-access",
    "distribution-settings",
    "company-uom-profile",
    "distribution-route",
    "distribution-master-scope",
    "customer",
    "supplier",
    "item",
    "item-price",
    "price-list",
    "purchase-receipt",
    "van-loading",
    "van-loading-challan",
    "van-loading-acknowledgement",
    "dsr-collection-receipt",
    "sr-order",
    "outlet-visit",
    "field-sales",
    "delivery-note",
    "return-inspection",
    "dsr-day-settlement",
    "user-profile",
    "user",
    "home",
  ]);

  function redirectToDistribution(route) {
    if (!route || !allowedRoutes.has(route[0])) {
      frappe.set_route("distribution");
    }
  }

  frappe.after_ajax(function () {
    frappe.call({
      method: "reckon_distribution.desk_guard.get_restricted_desk_context",
      callback: function (response) {
        var context = response.message || {};
        if (!context.restricted) {
          return;
        }

        redirectToDistribution(frappe.get_route());
        frappe.router.on("change", function () {
          redirectToDistribution(frappe.get_route());
        });
      },
    });
  });
})();
