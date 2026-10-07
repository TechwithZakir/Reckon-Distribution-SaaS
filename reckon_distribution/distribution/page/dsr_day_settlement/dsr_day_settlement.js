frappe.pages["dsr-day-settlement"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("DSR Day Settlement"), single_column: true });
  $(page.body).html(`<main class="rd-settlement-page"><p class="rd-kicker">${__("Route close")}</p><h2>${__("DSR Day Settlement")}</h2><p>${__("Reconcile van stock and DSR cash before manager approval.")}</p><a class="btn btn-primary" href="/app/dsr-day-settlement/new-dsr-day-settlement-1">${__("New settlement")}</a><a class="btn btn-default" href="/app/dsr-day-settlement">${__("Open settlements")}</a></main>`);
};
