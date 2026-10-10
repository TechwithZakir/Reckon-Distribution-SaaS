frappe.pages["distribution-master-setup"].on_page_load = function (wrapper) {
  frappe.require("/assets/reckon_distribution/css/distribution_pages.css");
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Setup Guide"), single_column: true });
  $(page.body).html(`<div class="rd-setup-guide rd-theme-page"><div class="rd-page-shell"><section class="rd-master-hero rd-page-header"><div><p class="rd-kicker">${__("Start here / এখান থেকে শুরু করুন")}</p><h2>${__("Distribution Setup Guide")}</h2><p>${__("Complete these simple steps in order. / নিচের ধাপগুলো ক্রমানুসারে শেষ করুন।")}</p></div><a class="btn btn-default" href="/desk/distribution">${__("Back to workspace")}</a></section><section class="rd-company-picker"><label>${__("Your Company / আপনার কোম্পানি")}<select data-company><option value="">${__("Select Company")}</option></select></label><button class="btn btn-primary" data-refresh>${__("Refresh status")}</button></section><div data-steps><p class="text-muted">${__("Select a Company to begin. / শুরু করতে কোম্পানি নির্বাচন করুন।")}</p></div></div><div class="rd-theme-modal" data-form hidden><div class="rd-theme-modal__dialog" role="dialog" aria-modal="true"><div class="rd-theme-modal__head"><h3 data-form-title></h3><button class="rd-theme-modal__close" type="button" data-close-form aria-label="${__("Close")}">×</button></div><div class="rd-theme-modal__body" data-form-body></div><div class="rd-theme-modal__foot" data-form-actions></div></div></div></div>`);
  const companySelect = $(page.body).find("[data-company]");
  let links = {};
  const requestedStep = new URLSearchParams(window.location.search).get("step");
  const requestedName = new URLSearchParams(window.location.search).get("name");
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => {
    const companies = r.message || [];
    companies.forEach((row) => companySelect.append(`<option value="${esc(row.name)}">${esc(row.name)}</option>`));
    if (companies.length === 1) {
      companySelect.val(companies[0].name).hide();
      $(page.body).find("[data-refresh]").hide();
      companySelect.after(`<span class="rd-company-fixed">${esc(companies[0].name)}</span>`);
      refresh();
    }
  });
  companySelect.on("change", refresh);
  $(page.body).find("[data-refresh]").on("click", refresh);
  $(page.body).on("click", "[data-step]", function () { const step = $(this).data("step"); step === "finish-setup" ? check_setup() : show_form(step); });
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
    ]).then(([status, linkData]) => { links = linkData.message || {}; render_steps(status.message); if (requestedStep) { const record = find_record(status.message, requestedStep, requestedName); show_form(requestedStep, record); } });
  }

  function render_steps(status) {
    const steps = [
      { number: "1", title: "Company rules", bangla: "কোম্পানির নিয়ম", help: "Set Company rules and manage Distribution Warehouses.", help_bn: "কোম্পানির নিয়ম সেট করুন এবং ডিস্ট্রিবিউশন গুদাম পরিচালনা করুন।", done: status.settings > 0, route: "distribution-settings" },
      { number: "2", title: "Field user access", bangla: "ফিল্ড ব্যবহারকারী", help: "Create the SR/DSR login and give it access to this Company.", help_bn: "SR/DSR লগইন তৈরি করে এই কোম্পানির অ্যাক্সেস দিন।", done: status.users > 0, route: "distribution-team-access", page: true },
      { number: "3", title: "Route", bangla: "রুট", help: "Open the native Frappe Route list. Company access is enforced on the server.", help_bn: "Frappe-এর নিজস্ব রুট তালিকা খুলুন। সার্ভারে কোম্পানি অ্যাক্সেস যাচাই হয়।", done: status.routes > 0, route: "distribution-route", records: status.records.routes, type: "route", native: "/desk/distribution-route" },
      { number: "4", title: "Retailers", bangla: "রিটেইলার", help: "Open the native ERPNext Customer list to create or edit shops.", help_bn: "দোকান তৈরি বা সম্পাদনা করতে ERPNext Customer তালিকা খুলুন।", done: status.retailers > 0, route: "customer", native: "/desk/customer" },
      { number: "5", title: "Suppliers", bangla: "সরবরাহকারী", help: "Open the native ERPNext Supplier list to create or edit suppliers.", help_bn: "সরবরাহকারী তৈরি বা সম্পাদনা করতে ERPNext Supplier তালিকা খুলুন।", done: status.suppliers > 0, route: "supplier", native: "/desk/supplier" },
      { number: "6", title: "Products", bangla: "পণ্য", help: "Open the native ERPNext Item list to create or edit products.", help_bn: "পণ্য তৈরি বা সম্পাদনা করতে ERPNext Item তালিকা খুলুন।", done: status.products > 0, route: "item", native: "/desk/item" },
      { number: "7", title: "Item units", bangla: "পণ্যের ইউনিট", help: "Add sales units and conversion factors for each product.", help_bn: "প্রতিটি পণ্যের বিক্রয় ইউনিট ও রূপান্তর অনুপাত দিন।", done: status.products > 0, route: "distribution-item-uom-setup", native: "/desk/distribution-item-uom-setup" },
      { number: "8", title: "Prices", bangla: "দাম", help: "Open the native ERPNext Item Price list to manage selling prices.", help_bn: "বিক্রয় মূল্য পরিচালনা করতে ERPNext Item Price তালিকা খুলুন।", done: status.prices > 0, route: "item-price", native: "/desk/item-price" },
      { number: "9", title: "Retailer route", bangla: "রিটেইলার রুটে যুক্ত করুন", help: "Assign the retailer, route and responsible field user.", help_bn: "রিটেইলার, রুট ও দায়িত্বপ্রাপ্ত ফিল্ড ব্যবহারকারী যুক্ত করুন।", done: status.assignments > 0, route: "retailer-route-assignment" },
      { number: "10", title: "Finish setup", bangla: "সেটআপ শেষ করুন", help: "Validate the Company setup and unlock field work.", help_bn: "কোম্পানি সেটআপ যাচাই করে ফিল্ড কাজ চালু করুন।", done: status.assignments > 0 && status.products > 0 && status.prices > 0, route: "finish-setup" },
    ];
    $(page.body).find("[data-steps]").html(steps.map((step) => `<article class="rd-setup-step ${step.done ? "is-done" : ""}"><div class="rd-setup-number">${step.number}</div><div class="rd-setup-copy"><h3>${__(step.title)} <span>${__(step.bangla)}</span></h3><p>${__(step.help)}<br><small>${__(step.help_bn)}</small></p></div><div class="rd-setup-action">${step.done ? `<strong>${__("Done / সম্পন্ন")}</strong>` : ""}${step.page ? `<a class="btn btn-default" href="/desk/${step.route}">${__("Open")}</a>` : step.native ? `<a class="btn btn-default" href="${step.native}">${__("Open native list")}</a>` : `<button class="btn ${step.done ? "btn-default" : "btn-primary"}" data-step="${step.route}">${step.done ? __("Review") : __("Set up")}</button>`}</div></article>`).join(""));
  }

  function find_record(status, step, name) {
    const source = { "distribution-route": status.records.routes, customer: status.records.retailers, "retailer-route-assignment": status.records.assignments_list, "distribution-master-scope": status.records.products }[step] || [];
    return source.find((row) => row.name === name);
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
      "distribution-settings": [__("Company rules / কোম্পানির নিয়ম"), "save_company_settings", `<p class="text-muted">${__("Choose the defaults used for this Company. Create warehouse records from the Distribution Warehouse setup.")}</p><label>${__("Default distribution warehouse / ডিফল্ট ডিস্ট্রিবিউশন গুদাম")}<select name="default_warehouse">${optionList(links.warehouses, "name", "warehouse_name", selected.default_warehouse, __("Optional"))}</select></label><label>${__("Sales price list / বিক্রয় মূল্য তালিকা")}<select name="default_price_list">${optionList(links.price_lists, "name", "price_list_name", selected.default_price_list, __("Optional"))}</select></label><label>${__("Receivable account / পাওনা হিসাব")}<select name="default_receivable_account">${optionList(links.accounts, "name", "account_name", selected.default_receivable_account, __("Optional"))}</select></label><label>${__("Cash custody account / নগদ হেফাজত হিসাব")}<select name="default_cash_account">${optionList(links.accounts, "name", "account_name", selected.default_cash_account, __("Optional"))}</select></label><a class="btn btn-default" href="/desk/warehouse">${__("Manage Distribution Warehouses")}</a>`],
      "distribution-route": [__("Create route / রুট তৈরি করুন"), "create_route", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Route code / রুট কোড")}<input required name="route_code" value="${esc(selected.route_code || "")}" placeholder="R-01" /></label><label>${__("Route name / রুটের নাম")}<input required name="route_name" value="${esc(selected.route_name || "")}" placeholder="Mirpur Route" /></label><label>${__("Assigned field user / দায়িত্বপ্রাপ্ত ব্যবহারকারী")}<select required name="assigned_user">${optionList(links.users, "user", "full_name", selected.assigned_user, __("Select field user"))}</select></label>`],
      "customer": [__("Retailer setup / রিটেইলার সেটআপ"), "create_retailer", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Shop name / দোকানের নাম")}<input required name="customer_name" value="${esc(selected.customer_name || "")}" placeholder="Rahim Store" /></label><label>${__("Shop code / দোকান কোড")}<input required name="outlet_code" value="${esc(selected.outlet_code || "")}" placeholder="SHOP-001" /></label><label>${__("Route / রুট")}<select name="route">${optionList(links.routes, "name", "route_name", selected.route, __("Optional"))}</select></label><label>${__("Area / এলাকা")}<select name="territory">${optionList(links.territories, "name", "name", selected.territory, __("Select area"))}</select></label><label>${__("Credit limit / ক্রেডিট সীমা")}<input name="credit_limit" type="number" min="0" step="0.01" value="${esc(selected.credit_limit || "")}" /></label><label>${__("Payment terms / পেমেন্ট শর্ত")}<select name="payment_terms">${optionList(links.payment_terms, "name", "template_name", selected.payment_terms, __("Optional"))}</select></label>`],
      "retailer-route-assignment": [__("Assign retailer to route / রুটে রিটেইলার যুক্ত করুন"), "assign_retailer", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Retailer / রিটেইলার")}<select required name="customer">${optionList(links.customers, "name", "customer_name", selected.customer, __("Select retailer"))}</select></label><label>${__("Route / রুট")}<select required name="route">${optionList(links.routes, "name", "route_name", selected.route, __("Select route"))}</select></label><label>${__("Field user / ফিল্ড ব্যবহারকারী")}<select required name="assigned_user">${optionList(links.users, "user", "full_name", selected.assigned_user, __("Select field user"))}</select></label>`],
      "product": [__("Product setup / পণ্য সেটআপ"), "create_product", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Product name / পণ্যের নাম")}<input required name="item_name" value="${esc(selected.item_name || "")}" placeholder="Biscuit 100g" /></label><label>${__("Sales unit / বিক্রয় ইউনিট")}<select required name="uom">${optionList(links.uoms, "name", "name", selected.stock_uom, __("Select UOM"))}</select></label><label>${__("Company product code / কোম্পানি পণ্য কোড")}<input name="company_item_code" value="${esc(selected.company_item_code || "")}" placeholder="ITEM-001" /></label>`],
      "price": [__("Price setup / মূল্য সেটআপ"), "create_price", `<label>${__("Product / পণ্য")}<select required name="item">${optionList(links.items, "name", "item_name", selected.item, __("Select product"))}</select></label><label>${__("Price list / মূল্য তালিকা")}<select required name="price_list">${optionList(links.price_lists, "name", "price_list_name", selected.price_list, __("Select price list"))}</select></label><label>${__("Sales unit / বিক্রয় ইউনিট")}<select required name="uom">${optionList(links.uoms, "name", "name", selected.uom, __("Select UOM"))}</select></label><label>${__("Selling price / বিক্রয় মূল্য")}<input required name="rate" type="number" min="0" step="0.01" value="${esc(selected.rate || "")}" /></label><label>${__("Valid from / কার্যকর শুরু")}<input name="valid_from" type="date" value="${esc(selected.valid_from || "")}" /></label><label>${__("Valid to / কার্যকর শেষ")}<input name="valid_to" type="date" value="${esc(selected.valid_to || "")}" /></label>`],
      "supplier": [__("Supplier setup / সরবরাহকারী সেটআপ"), "create_supplier", `<input type="hidden" name="name" value="${esc(selected.name || "")}" /><label>${__("Supplier name / সরবরাহকারীর নাম")}<input required name="supplier_name" value="${esc(selected.supplier_name || "")}" placeholder="ABC Foods Ltd." /></label><label>${__("Supplier code / সরবরাহকারী কোড")}<input required name="supplier_code" value="${esc(selected.supplier_code || "")}" placeholder="SUP-001" /></label><label>${__("Purchase terms / ক্রয় শর্ত")}<select name="payment_terms">${optionList(links.payment_terms, "name", "template_name", selected.payment_terms, __("Optional"))}</select></label>`],
    };
    const form = forms[step];
    if (!form) return;
    const box = $(page.body).find("[data-form]");
    box.prop("hidden", false);
    box.find("[data-form-title]").text(form[0]);
    box.find("[data-form-body]").html(`<p class="text-muted">${record ? __("Edit this Company record. / এই কোম্পানি রেকর্ড সম্পাদনা করুন।") : __("Use the linked choices so the server can validate this record. / লিঙ্ক করা অপশন ব্যবহার করুন।")}</p><div class="rd-inline-fields">${form[2]}</div>`);
    box.find("[data-form-actions]").html(`<button class="btn btn-primary" data-save-form>${record ? __("Save changes") : __("Save / সংরক্ষণ")}</button><button class="btn btn-default" data-close-form>${__("Cancel")}</button>`);
    box.find("[data-close-form]").on("click", () => box.prop("hidden", true));
    box.find("[data-save-form]").on("click", () => {
      const payload = { company: companySelect.val() };
      box.find("[name]").each(function () { payload[this.name] = this.value; });
      frappe.call({ method: `reckon_distribution.setup_guide.${form[1]}`, args: { payload: JSON.stringify(payload) } }).then(() => { box.html(`<p class="text-success">${__("Saved. Refreshing the setup status. / সংরক্ষণ হয়েছে।")}</p>`); refresh(); }).catch(() => frappe.msgprint(__("Please check the fields and your Company access.")));
    });
    box[0].scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function check_setup() {
    const company = companySelect.val();
    frappe.call({ method: "reckon_distribution.setup_guide.get_setup_status", args: { company } }).then((r) => {
      const s = r.message;
      const missing = [];
      if (!s.settings) missing.push(__("Company rules"));
      if (!s.users) missing.push(__("Team member"));
      if (!s.routes) missing.push(__("Route"));
      if (!s.retailers) missing.push(__("Retailer"));
      if (!s.assignments) missing.push(__("Retailer route assignment"));
      if (!s.products) missing.push(__("Product"));
      if (!s.prices) missing.push(__("Price"));
      if (!s.suppliers) missing.push(__("Supplier"));
      const box = $(page.body).find("[data-form]").prop("hidden", false);
      box.html(missing.length ? `<h3>${__("Finish setup / সেটআপ শেষ করুন")}</h3><p class="text-warning">${__("Complete these steps first / আগে এই ধাপগুলো শেষ করুন:")} ${missing.join(", ")}</p>` : `<h3>${__("Setup complete / সেটআপ সম্পন্ন")}</h3><p class="text-success">${__("Your Company setup is ready for field work. / আপনার কোম্পানি ফিল্ড কাজের জন্য প্রস্তুত।")}</p><a class="btn btn-primary" href="/desk/dsr-delivery">${__("Open field work")}</a>`);
      box[0].scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function esc(value) { return frappe.utils.escape_html(String(value == null ? "" : value)); }
};
