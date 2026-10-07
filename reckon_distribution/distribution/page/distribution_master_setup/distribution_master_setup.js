frappe.pages["distribution-master-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Setup Guide"), single_column: true });
  $(page.body).html(`<div class="rd-setup-guide"><section class="rd-master-hero"><div><p class="rd-kicker">${__("Start here / এখান থেকে শুরু করুন")}</p><h2>${__("Distribution Setup Guide")}</h2><p>${__("Complete these simple steps in order. / নিচের ধাপগুলো ক্রমানুসারে শেষ করুন।")}</p></div><a class="btn btn-default" href="/app/distribution">${__("Back to workspace")}</a></section><section class="rd-company-picker"><label>${__("Your Company / আপনার কোম্পানি")}<select data-company><option value="">${__("Select Company")}</option></select></label><button class="btn btn-primary" data-refresh>${__("Refresh status")}</button></section><div data-steps><p class="text-muted">${__("Select a Company to begin. / শুরু করতে কোম্পানি নির্বাচন করুন।")}</p></div><section class="rd-inline-form" data-form hidden></section></div>`);
  const companySelect = $(page.body).find("[data-company]");
  let links = {};
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => {
    (r.message || []).forEach((row) => companySelect.append(`<option value="${esc(row.name)}">${esc(row.name)}</option>`));
    if ((r.message || []).length === 1) { companySelect.val(r.message[0].name); refresh(); }
  });
  companySelect.on("change", refresh);
  $(page.body).find("[data-refresh]").on("click", refresh);
  $(page.body).on("click", "[data-step]", function () { show_form($(this).data("step")); });
  $(page.body).on("click", "[data-edit-record]", function () { show_form($(this).data("edit-record"), JSON.parse($(this).attr("data-record"))); });
  $(page.body).on("click", "[data-remove-record]", function () {
    const button = $(this);
    frappe.confirm(__("Remove this Company setup entry? / এই কোম্পানির সেটআপ এন্ট্রি সরাবেন?"), () => {
      frappe.call({ method: "reckon_distribution.setup_guide.remove_setup_entry", args: { company: companySelect.val(), entry_type: button.data("remove-record"), name: button.data("name") } }).then(refresh);
    });
  });

  function refresh() {
    const company = companySelect.val();
    if (!company) return;
    Promise.all([
      frappe.call({ method: "reckon_distribution.setup_guide.get_setup_status", args: { company } }),
      frappe.call({ method: "reckon_distribution.setup_guide.get_setup_links", args: { company } }),
    ]).then(([status, linkData]) => { links = linkData.message || {}; render_steps(status.message); });
  }

  function render_steps(status) {
    const steps = [
      { number: "1", title: "Company rules", bangla: "কোম্পানির নিয়ম", help: "Set warehouse, accounts and payment defaults.", help_bn: "গুদাম, হিসাব ও পেমেন্টের নিয়ম ঠিক করুন।", done: status.settings > 0, route: "distribution-settings" },
      { number: "2", title: "Field user access", bangla: "ফিল্ড ব্যবহারকারী", help: "Create the SR/DSR login and give it access to this Company.", help_bn: "SR/DSR লগইন তৈরি করে এই কোম্পানির অ্যাক্সেস দিন।", done: status.users > 0, route: "distribution-team-access", page: true },
      { number: "3", title: "Route", bangla: "রুট", help: "Create the route and assign the SR/DSR who works on it.", help_bn: "রুট তৈরি করে দায়িত্বপ্রাপ্ত SR/DSR নির্বাচন করুন।", done: status.routes > 0, route: "distribution-route", records: status.records.routes, type: "route" },
      { number: "4", title: "Retailer", bangla: "রিটেইলার", help: "Create the shop/customer record.", help_bn: "দোকান/কাস্টমার রেকর্ড তৈরি করুন।", done: status.retailers > 0, route: "customer", records: status.records.retailers, type: "retailer" },
      { number: "5", title: "Retailer route", bangla: "রিটেইলার রুটে যুক্ত করুন", help: "Assign the retailer to the route and field user.", help_bn: "রিটেইলারকে রুট ও ফিল্ড ব্যবহারকারীর সাথে যুক্ত করুন।", done: status.assignments > 0, route: "retailer-route-assignment", records: status.records.assignments_list, type: "assignment" },
      { number: "6", title: "Products and prices", bangla: "পণ্য ও দাম", help: "Enable products, price list and sales UOMs for this Company.", help_bn: "কোম্পানির জন্য পণ্য, মূল্য তালিকা ও বিক্রয় UOM চালু করুন।", done: status.products > 0 && status.prices > 0, route: "distribution-master-scope", records: status.records.products, type: "product" },
      { number: "7", title: "Start field work", bangla: "ফিল্ড কাজ শুরু করুন", help: "Open the delivery page. Assigned retailers will appear here.", help_bn: "ডেলিভারি পেজ খুলুন। দায়িত্বপ্রাপ্ত রিটেইলার এখানে দেখা যাবে।", done: status.assignments > 0 && status.products > 0, route: "dsr-delivery", page: true },
    ];
    $(page.body).find("[data-steps]").html(steps.map((step) => `<article class="rd-setup-step ${step.done ? "is-done" : ""}"><div class="rd-setup-number">${step.number}</div><div class="rd-setup-copy"><h3>${__(step.title)} <span>${__(step.bangla)}</span></h3><p>${__(step.help)}<br><small>${__(step.help_bn)}</small></p>${render_records(step)}</div><div class="rd-setup-action">${step.done ? `<strong>${__("Done / সম্পন্ন")}</strong>` : ""}${step.page ? `<a class="btn btn-default" href="/desk/${step.route}">${__("Open")}</a>` : `<button class="btn ${step.done ? "btn-default" : "btn-primary"}" data-step="${step.route}">${step.done ? __("Review") : __("Set up")}</button>`}</div></article>`).join(""));
  }

  function render_records(step) {
    if (!step.records) return "";
    if (!step.records.length) return `<p class="rd-record-empty">${__("No records yet. Add the first one above. / এখনো কোনো রেকর্ড নেই।")}</p>`;
    return `<div class="rd-record-list">${step.records.map((row) => {
      const label = row.customer_name || row.item_name || row.route_name || row.name;
      const detail = row.route ? `${row.customer} → ${row.route}` : (row.assigned_user || row.stock_uom || "");
      return `<div class="rd-record-row"><div><strong>${esc(label)}</strong><small>${esc(detail)}</small></div><span><button class="btn btn-default btn-xs" data-edit-record="${step.route}" data-record='${esc(JSON.stringify(row))}'>${__("Edit")}</button><button class="btn btn-danger btn-xs" data-remove-record="${step.type}" data-name="${esc(row.name)}">${__("Remove")}</button></span></div>`;
    }).join("")}</div>`;
  }

  function optionList(values, valueKey, labelKey, selected, empty) {
    const first = `<option value="">${empty || __("Select")}</option>`;
    return first + (values || []).map((row) => `<option value="${esc(row[valueKey])}" ${row[valueKey] === selected ? "selected" : ""}>${esc(row[labelKey] || row[valueKey])}</option>`).join("");
  }

  function show_form(step, record) {
    const selected = record || {};
    const forms = {
      "distribution-settings": [__("Company rules / কোম্পানির নিয়ম"), "save_company_settings", `<label>${__("Default warehouse / ডিফল্ট গুদাম")}<select name="default_warehouse">${optionList(links.warehouses, "name", "warehouse_name", selected.default_warehouse, __("Optional"))}</select></label><label>${__("Sales price list / বিক্রয় মূল্য তালিকা")}<select name="default_price_list">${optionList(links.price_lists, "name", "price_list_name", selected.default_price_list, __("Optional"))}</select></label><label>${__("Receivable account / পাওনা হিসাব")}<select name="default_receivable_account">${optionList(links.accounts, "name", "account_name", selected.default_receivable_account, __("Optional"))}</select></label><label>${__("Cash custody account / নগদ হেফাজত হিসাব")}<select name="default_cash_account">${optionList(links.accounts, "name", "account_name", selected.default_cash_account, __("Optional"))}</select></label>`],
      "distribution-route": [__("Create route / রুট তৈরি করুন"), "create_route", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Route code / রুট কোড")}<input required name="route_code" value="${esc(selected.route_code || "")}" placeholder="R-01" /></label><label>${__("Route name / রুটের নাম")}<input required name="route_name" value="${esc(selected.route_name || "")}" placeholder="Mirpur Route" /></label><label>${__("Assigned field user / দায়িত্বপ্রাপ্ত ব্যবহারকারী")}<select required name="assigned_user">${optionList(links.users, "user", "full_name", selected.assigned_user, __("Select field user"))}</select></label>`],
      "customer": [__("Add retailer / রিটেইলার যোগ করুন"), "create_retailer", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Shop name / দোকানের নাম")}<input required name="customer_name" value="${esc(selected.customer_name || "")}" placeholder="Rahim Store" /></label><label>${__("Customer group / কাস্টমার গ্রুপ")}<select name="customer_group">${optionList(links.customer_groups, "name", "name", selected.customer_group, __("Select group"))}</select></label><label>${__("Area / এলাকা")}<select name="territory">${optionList(links.territories, "name", "name", selected.territory, __("Select area"))}</select></label>`],
      "retailer-route-assignment": [__("Assign retailer to route / রুটে রিটেইলার যুক্ত করুন"), "assign_retailer", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Retailer / রিটেইলার")}<select required name="customer">${optionList(links.customers, "name", "customer_name", selected.customer, __("Select retailer"))}</select></label><label>${__("Route / রুট")}<select required name="route">${optionList(links.routes, "name", "route_name", selected.route, __("Select route"))}</select></label><label>${__("Field user / ফিল্ড ব্যবহারকারী")}<select required name="assigned_user">${optionList(links.users, "user", "full_name", selected.assigned_user, __("Select field user"))}</select></label>`],
      "distribution-master-scope": [__("Add product and price / পণ্য ও দাম যোগ করুন"), "create_product", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Product name / পণ্যের নাম")}<input required name="item_name" value="${esc(selected.item_name || "")}" placeholder="Biscuit 100g" /></label><label>${__("Sales unit / বিক্রয় ইউনিট")}<select required name="uom">${optionList(links.uoms, "name", "name", selected.stock_uom, __("Select UOM"))}</select></label><label>${__("Selling price / বিক্রয় মূল্য")}<input required name="price" type="number" min="0" step="0.01" value="${esc(selected.price || "")}" placeholder="25" /></label><label>${__("Price list / মূল্য তালিকা")}<select name="price_list">${optionList(links.price_lists, "name", "price_list_name", selected.price_list, __("Select price list"))}</select></label>`],
    };
    const form = forms[step];
    if (!form) return;
    const box = $(page.body).find("[data-form]");
    box.prop("hidden", false).html(`<h3>${form[0]}</h3><p class="text-muted">${record ? __("Edit this Company record. / এই কোম্পানি রেকর্ড সম্পাদনা করুন।") : __("Use the linked choices so the server can validate this record. / লিঙ্ক করা অপশন ব্যবহার করুন।")}</p><div class="rd-inline-fields">${form[2]}</div><button class="btn btn-primary" data-save-form>${record ? __("Save changes") : __("Save / সংরক্ষণ")}</button><button class="btn btn-default" data-close-form>${__("Close")}</button>`);
    box.find("[data-close-form]").on("click", () => box.prop("hidden", true));
    box.find("[data-save-form]").on("click", () => {
      const payload = { company: companySelect.val() };
      box.find("[name]").each(function () { payload[this.name] = this.value; });
      frappe.call({ method: `reckon_distribution.setup_guide.${form[1]}`, args: { payload: JSON.stringify(payload) } }).then(() => { box.html(`<p class="text-success">${__("Saved. Refreshing the setup status. / সংরক্ষণ হয়েছে।")}</p>`); refresh(); }).catch(() => frappe.msgprint(__("Please check the fields and your Company access.")));
    });
    box[0].scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function esc(value) { return frappe.utils.escape_html(String(value == null ? "" : value)); }
};
