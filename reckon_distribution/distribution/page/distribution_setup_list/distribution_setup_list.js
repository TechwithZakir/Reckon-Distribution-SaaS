frappe.pages["distribution-setup-list"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Setup records"), single_column: true });
  const query = new URLSearchParams(window.location.search);
  const type = query.get("type") || "route";
  const config = {
    route: { title: __("Routes / রুট"), plural: __("routes / রুট"), setup: "distribution-route", columns: ["route_name", "route_code", "assigned_user"] },
    retailer: { title: __("Retailers / রিটেইলার"), plural: __("retailers / রিটেইলার"), setup: "customer", columns: ["customer_name", "customer_group", "territory"] },
    assignment: { title: __("Retailer route assignments / রুটে রিটেইলার"), plural: __("assignments / অ্যাসাইনমেন্ট"), setup: "retailer-route-assignment", columns: ["customer", "route", "assigned_user"] },
    product: { title: __("Products and prices / পণ্য ও দাম"), plural: __("products / পণ্য"), setup: "distribution-master-scope", columns: ["item_name", "stock_uom"] },
  }[type] || null;
  if (!config) { $(page.body).html(`<p class="text-danger">${__("Unsupported setup list.")}</p>`); return; }
  $(page.body).html(`<main class="rd-setup-list"><header class="rd-setup-list-hero"><div><p class="rd-kicker">${__("Company setup / কোম্পানি সেটআপ")}</p><h2>${config.title}</h2><p>${__("Manage records saved for the selected Company. / নির্বাচিত কোম্পানির সংরক্ষিত রেকর্ড পরিচালনা করুন।")}</p></div><a class="btn btn-default" href="/desk/distribution-master-setup">${__("Back to guide")}</a></header><section class="rd-company-picker"><label>${__("Company / কোম্পানি")}<select data-company><option value="">${__("Select Company")}</option></select></label><button class="btn btn-primary" data-add>${__("Add new")}</button></section><section class="rd-setup-table" data-table><p class="text-muted">${__("Select a Company. / কোম্পানি নির্বাচন করুন।")}</p></section></main>`);
  const company = $(page.body).find("[data-company]");
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => {
    (r.message || []).forEach((row) => company.append(`<option value="${esc(row.name)}">${esc(row.name)}</option>`));
    if ((r.message || []).length === 1) { company.val(r.message[0].name); load(); }
  });
  company.on("change", load);
  $(page.body).find("[data-add]").on("click", () => window.location.href = `/desk/distribution-master-setup?step=${config.setup}`);

  function load() {
    if (!company.val()) return;
    frappe.call({ method: "reckon_distribution.setup_guide.get_setup_records", args: { company: company.val(), entry_type: type } }).then((r) => {
      const rows = r.message || [];
      if (!rows.length) { $(page.body).find("[data-table]").html(`<p class="text-muted">${__("No records yet. Use Add new. / এখনো কোনো রেকর্ড নেই।")}</p>`); return; }
      const head = config.columns.map((field) => `<th>${esc(field.replaceAll("_", " "))}</th>`).join("");
      const body = rows.map((row) => `<tr>${config.columns.map((field) => `<td>${esc(row[field] || "")}</td>`).join("")}<td class="rd-setup-list-actions"><a class="btn btn-default btn-xs" href="/desk/distribution-master-setup?step=${config.setup}&name=${encodeURIComponent(row.name)}">${__("Edit")}</a><button class="btn btn-danger btn-xs" data-remove="${esc(row.name)}">${__("Remove")}</button></td></tr>`).join("");
      $(page.body).find("[data-table]").html(`<table class="table table-bordered"><thead><tr>${head}<th>${__("Actions")}</th></tr></thead><tbody>${body}</tbody></table>`);
      $(page.body).find("[data-remove]").on("click", function () { const name = $(this).data("remove"); frappe.confirm(__("Remove this Company setup entry? / এই কোম্পানির সেটআপ এন্ট্রি সরাবেন?"), () => frappe.call({ method: "reckon_distribution.setup_guide.remove_setup_entry", args: { company: company.val(), entry_type: type, name } }).then(load)); });
    });
  }
  function esc(value) { return frappe.utils.escape_html(String(value == null ? "" : value)); }
};
