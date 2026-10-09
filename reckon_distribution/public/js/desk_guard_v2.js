(function () {
  // Desk navigation is authorized by the server-side before_request guard.
  // This client check covers SPA route changes that do not make an HTTP request.
  const allowedAppRoutes = new Set([
    "distribution",
    "distribution-master-setup",
    "distribution-team-access",
    "distribution-settings",
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
    "dsr-delivery",
    "delivery-note",
    "return-inspection",
    "dsr-day-settlement",
    "user-profile",
    "home",
  ]);
  const hiddenRoutes = new Set([
    "tenant-security-test-record",
    "distribution-master-scope",
    "company-uom-profile",
    "undefined",
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
      const route = routeName(link.href);
      const item = link.closest(".sidebar-item, .standard-sidebar-item, li");
      if (!item) return;

      const label = (link.textContent || "").trim().toLowerCase();
      const isTechnicalRecord =
        hiddenRoutes.has(route) || label.includes("company uom profile");

      // The server is authoritative; this removes stale or unrelated native
      // links from an already-rendered tenant sidebar after SPA navigation.
      if (isTechnicalRecord || (route && !allowedAppRoutes.has(route))) {
        item.style.display = "none";
      }
    });
  }

  function applyDenseFormLayout() {
    const desktop = window.innerWidth >= 992;
    const tablet = window.innerWidth >= 768;
    const columns = desktop ? 3 : tablet ? 2 : 1;

    document
      .querySelectorAll(".layout-main-section, .layout-main-section-wrapper, .form-layout")
      .forEach((element) => {
        element.style.setProperty("width", "100%", "important");
        element.style.setProperty("max-width", "none", "important");
      });

    document.querySelectorAll(".form-layout .form-section").forEach((section) => {
      const body = section.querySelector(":scope > .section-body") || section;
      section.style.setProperty("width", "100%", "important");
      section.style.setProperty("max-width", "none", "important");
      body.style.setProperty("width", "100%", "important");
      body.style.setProperty("max-width", "none", "important");
      body.style.setProperty("display", "grid", "important");
      body.style.setProperty(
        "grid-template-columns",
        `repeat(${columns}, minmax(0, 1fr))`,
        "important"
      );
      body.style.setProperty("column-gap", desktop ? "24px" : "20px", "important");
      body.style.setProperty("row-gap", "4px", "important");

      section.querySelectorAll(".form-column").forEach((column) => {
        column.style.setProperty("display", "contents", "important");
        column.style.setProperty("float", "none", "important");
        column.style.setProperty("width", "auto", "important");
      });

      section.querySelectorAll(".frappe-control").forEach((control) => {
        control.style.setProperty("width", "auto", "important");
        control.style.setProperty("min-width", "0", "important");
        if (control.querySelector(".grid-field")) {
          control.style.setProperty("grid-column", "1 / -1", "important");
        }
      });
    });
  }

  function enforceDistributionRoute() {
    if (window.location.pathname === "/desk/undefined") {
      window.location.replace("/desk/distribution");
      return;
    }

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
    applyDenseFormLayout();
    [100, 300, 700, 1200].forEach((delay) => window.setTimeout(applyDenseFormLayout, delay));
    enforceDistributionRoute();
  });
  new MutationObserver(function () {
    hideInternalSidebarLinks();
    applyDenseFormLayout();
  }).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  window.addEventListener("popstate", enforceDistributionRoute);
  window.addEventListener("resize", applyDenseFormLayout);
  const installRouterGuard = window.setInterval(function () {
    if (!window.frappe || !frappe.router || typeof frappe.router.on !== "function") {
      return;
    }
    frappe.router.on("change", enforceDistributionRoute);
    frappe.router.on("change", applyDenseFormLayout);
    frappe.router.on("change", function () {
      [100, 300, 700, 1200].forEach((delay) => window.setTimeout(applyDenseFormLayout, delay));
    });
    window.clearInterval(installRouterGuard);
    enforceDistributionRoute();
  }, 100);
})();
