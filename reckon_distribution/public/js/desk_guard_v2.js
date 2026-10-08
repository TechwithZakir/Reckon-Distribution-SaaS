(function () {
  // Desk navigation is authorized by the server-side before_request guard.
  // This client check covers SPA route changes that do not make an HTTP request.
  const allowedAppRoutes = new Set([
    "distribution",
    "distribution-master-setup",
    "distribution-team-access",
    "distribution-settings",
    "company-uom-profile",
    "distribution-route",
    "customer",
    "supplier",
    "item",
    "item-price",
    "distribution-item-uom-setup",
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
    "home",
  ]);
  const hiddenRoutes = new Set([
    "tenant-security-test-record",
    "distribution-master-scope",
  ]);

  function routeName(href) {
    try {
      const url = new URL(href, window.location.origin);
      const match = url.pathname.match(/^\/(?:app|desk)\/([^/]+)/);
      return match ? decodeURIComponent(match[1]).toLowerCase() : "";
    } catch (error) {
      return "";
    }
  }

  function hideInternalSidebarLinks() {
    document.querySelectorAll("a[href]").forEach((link) => {
      if (hiddenRoutes.has(routeName(link.href))) {
        const item = link.closest(".sidebar-item, .standard-sidebar-item, li");
        (item || link).style.display = "none";
      }
    });
  }

  function enforceDistributionRoute() {
    const match = window.location.pathname.match(/^\/app\/([^/]+)/);
    if (!match || allowedAppRoutes.has(decodeURIComponent(match[1]).toLowerCase())) {
      return;
    }

    if (window.frappe && typeof frappe.set_route === "function") {
      frappe.set_route("distribution");
    } else {
      window.location.replace("/desk/distribution");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    hideInternalSidebarLinks();
    enforceDistributionRoute();
  });
  new MutationObserver(hideInternalSidebarLinks).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.addEventListener("popstate", enforceDistributionRoute);
  const installRouterGuard = window.setInterval(function () {
    if (!window.frappe || !frappe.router || typeof frappe.router.on !== "function") {
      return;
    }
    frappe.router.on("change", enforceDistributionRoute);
    window.clearInterval(installRouterGuard);
    enforceDistributionRoute();
  }, 100);
})();
