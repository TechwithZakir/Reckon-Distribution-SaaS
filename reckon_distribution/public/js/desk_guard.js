(function () {
  function redirectToDistribution(route) {
    if (!route || route[0] !== "distribution") {
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
