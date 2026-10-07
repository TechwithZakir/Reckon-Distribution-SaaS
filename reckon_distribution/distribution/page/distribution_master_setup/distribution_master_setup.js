frappe.pages["distribution-master-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Setup Guide"),
    single_column: true,
  });

  $(page.body).html(`<div class="rd-setup-guide"><section class="rd-master-hero"><div><p class="rd-kicker">${__("Start here / এখান থেকে শুরু করুন")}</p><h2>${__("Distribution Setup Guide")}</h2><p>${__("Complete these simple steps in order. / নিচের ধাপগুলো ক্রমানুসারে শেষ করুন।")}</p></div><a class="btn btn-default" href="/app/distribution">${__("Back to workspace")}</a></section><section class="rd-company-picker"><label>${__("Your Company / আপনার কোম্পানি")}</label><select data-company><option>${__("Select Company")}</option></select><button class="btn btn-primary" data-refresh>${__("Refresh status")}</button></section><div data-steps><p class="text-muted">${__("Select a Company to begin. / শুরু করতে কোম্পানি নির্বাচন করুন।")}</p></div><section class="rd-inline-form" data-form hidden></section></div>`);

  const companySelect = $(page.body).find("[data-company]");
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => {
    (r.message || []).forEach((row) => companySelect.append(`<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(row.name)}</option>`));
  });
  companySelect.on("change", refresh);
  $(page.body).find("[data-refresh]").on("click", refresh);
  $(page.body).on("click", "[data-step]", function () { show_form($(this).data("step")); });

  function refresh() {
    const company = companySelect.val();
    if (!company || company === "Select Company") return;
    frappe.call({ method: "reckon_distribution.setup_guide.get_setup_status", args: { company } }).then((r) => render_steps(r.message));
  }

  function render_steps(status) {
    const steps = [
      { number: "1", title: "Company rules", bangla: "কোম্পানির নিয়ম", help: "Set supplier-goods policy, warehouse, accounts and payment defaults.", help_bn: "সরবরাহকারীর পণ্য, গুদাম, হিসাব ও পেমেন্টের নিয়ম ঠিক করুন।", done: status.settings > 0, route: "distribution-settings" },
      { number: "2", title: "Field user access", bangla: "ফিল্ড ব্যবহারকারী", help: "Create the SR/DSR login and give it access to this Company.", help_bn: "SR/DSR লগইন তৈরি করে এই কোম্পানির অ্যাক্সেস দিন।", done: status.users > 0, route: "distribution-team-access", page: true },
      { number: "3", title: "Route", bangla: "রুট", help: "Create the route and assign the SR/DSR who works on it.", help_bn: "রুট তৈরি করে দায়িত্বপ্রাপ্ত SR/DSR নির্বাচন করুন।", done: status.routes > 0, route: "distribution-route" },
      { number: "4", title: "Retailer", bangla: "রিটেইলার", help: "Create the shop/customer record.", help_bn: "দোকান/কাস্টমার রেকর্ড তৈরি করুন।", done: status.retailers > 0, route: "customer" },
      { number: "5", title: "Retailer route", bangla: "রিটেইলার রুটে যুক্ত করুন", help: "Assign the retailer to the route and field user for today.", help_bn: "রিটেইলারকে আজকের রুট ও ফিল্ড ব্যবহারকারীর সাথে যুক্ত করুন।", done: status.assignments > 0, route: "retailer-route-assignment" },
      { number: "6", title: "Products and prices", bangla: "পণ্য ও দাম", help: "Enable products, price list and sales UOMs for this Company.", help_bn: "কোম্পানির জন্য পণ্য, মূল্য তালিকা ও বিক্রয় UOM চালু করুন।", done: status.products > 0 && status.prices > 0, route: "distribution-master-scope" },
      { number: "7", title: "Start field work", bangla: "ফিল্ড কাজ শুরু করুন", help: "Open the delivery page. Assigned retailers will appear here.", help_bn: "ডেলিভারি পেজ খুলুন। দায়িত্বপ্রাপ্ত রিটেইলার এখানে দেখা যাবে।", done: status.assignments > 0 && status.products > 0, route: "dsr-delivery" },
    ];
    $(page.body).find("[data-steps]").html(steps.map((step) => `<article class="rd-setup-step ${step.done ? "is-done" : ""}"><div class="rd-setup-number">${step.number}</div><div class="rd-setup-copy"><h3>${__(step.title)} <span>${__(step.bangla)}</span></h3><p>${__(step.help)}<br><small>${__(step.help_bn)}</small></p></div><div class="rd-setup-action">${step.done ? `<strong>${__("Done / সম্পন্ন")}</strong>` : ""}${step.page ? `<a class="btn btn-default" href="/desk/${step.route}">${__("Open")}</a>` : `<button class="btn ${step.done ? "btn-default" : "btn-primary"}" data-step="${step.route}">${step.done ? __("Review") : __("Set up")}</button>`}</div></article>`).join(""));
  }

  function show_form(step) {
    const forms = {
      "distribution-settings": [__("Company rules / কোম্পানির নিয়ম"), "save_company_settings", `<label>${__("Default warehouse / ডিফল্ট গুদাম")}<input name="default_warehouse" placeholder="Optional" /></label><label>${__("Sales price list / বিক্রয় মূল্য তালিকা")}<input name="default_price_list" placeholder="Optional" /></label><label>${__("Receivable account / পাওনা হিসাব")}<input name="default_receivable_account" placeholder="Optional" /></label><label>${__("Cash custody account / নগদ হেফাজত হিসাব")}<input name="default_cash_account" placeholder="Optional" /></label>`],
      "distribution-route": [__("Create route / রুট তৈরি করুন"), "create_route", `<label>${__("Route code / রুট কোড")}<input required name="route_code" placeholder="R-01" /></label><label>${__("Route name / রুটের নাম")}<input required name="route_name" placeholder="Mirpur Route" /></label><label>${__("Assigned field user email / দায়িত্বপ্রাপ্ত ইমেইল")}<input required name="assigned_user" placeholder="dsr@example.com" /></label>`],
      "customer": [__("Add retailer / রিটেইলার যোগ করুন"), "create_retailer", `<label>${__("Shop name / দোকানের নাম")}<input required name="customer_name" placeholder="Rahim Store" /></label><label>${__("Customer group / কাস্টমার গ্রুপ")}<input name="customer_group" placeholder="All Customer Groups" /></label><label>${__("Area / এলাকা")}<input name="territory" placeholder="All Territories" /></label>`],
      "retailer-route-assignment": [__("Assign retailer to route / রুটে রিটেইলার যুক্ত করুন"), "assign_retailer", `<label>${__("Retailer name / রিটেইলার")}<input required name="customer" placeholder="Exact retailer name" /></label><label>${__("Route name / রুট")}<input required name="route" placeholder="Company-R-01" /></label><label>${__("Field user email / ফিল্ড ব্যবহারকারী")}<input required name="assigned_user" placeholder="dsr@example.com" /></label>`],
      "distribution-master-scope": [__("Add product and price / পণ্য ও দাম যোগ করুন"), "create_product", `<label>${__("Product name / পণ্যের নাম")}<input required name="item_name" placeholder="Biscuit 100g" /></label><label>${__("Sales unit / বিক্রয় ইউনিট")}<input required name="uom" placeholder="Nos" /></label><label>${__("Selling price / বিক্রয় মূল্য")}<input required name="price" type="number" min="0" step="0.01" placeholder="25" /></label><label>${__("Price list (optional) / মূল্য তালিকা")}<input name="price_list" placeholder="Default sales list" /></label>`],
    };
    const form = forms[step];
    if (!form) return;
    const box = $(page.body).find("[data-form]");
    box.prop("hidden", false).html(`<h3>${form[0]}</h3><p class="text-muted">${__("Save this step, then refresh status. / এই ধাপ সেভ করে স্ট্যাটাস রিফ্রেশ করুন।")}</p><div class="rd-inline-fields">${form[2]}</div><button class="btn btn-primary" data-save-form>${__("Save / সংরক্ষণ")}</button><button class="btn btn-default" data-close-form>${__("Close")}</button>`);
    box.find("[data-close-form]").on("click", () => box.prop("hidden", true));
    box.find("[data-save-form]").on("click", () => {
      const payload = { company: companySelect.val() };
      box.find("[name]").each(function () { payload[this.name] = this.value; });
      frappe.call({ method: `reckon_distribution.setup_guide.${form[1]}`, args: { payload: JSON.stringify(payload) } }).then(() => { box.html(`<p class="text-success">${__("Saved. Refresh the setup status. / সংরক্ষণ হয়েছে।")}</p>`); refresh(); }).catch(() => frappe.msgprint(__("Please check the fields and your Company access.")));
    });
    box[0].scrollIntoView({ behavior: "smooth", block: "start" });
  }
};
