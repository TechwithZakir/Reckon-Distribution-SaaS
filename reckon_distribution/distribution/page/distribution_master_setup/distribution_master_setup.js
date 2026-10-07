frappe.pages["distribution-master-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Setup Guide"),
    single_column: true,
  });

  $(page.body).html(`<div class="rd-setup-guide"><section class="rd-master-hero"><div><p class="rd-kicker">${__("Start here / এখান থেকে শুরু করুন")}</p><h2>${__("Distribution Setup Guide")}</h2><p>${__("Complete these simple steps in order. / নিচের ধাপগুলো ক্রমানুসারে শেষ করুন।")}</p></div><a class="btn btn-default" href="/app/distribution">${__("Back to workspace")}</a></section><section class="rd-company-picker"><label>${__("Your Company / আপনার কোম্পানি")}</label><select data-company><option>${__("Select Company")}</option></select><button class="btn btn-primary" data-refresh>${__("Refresh status")}</button></section><div data-steps><p class="text-muted">${__("Select a Company to begin. / শুরু করতে কোম্পানি নির্বাচন করুন।")}</p></div></div>`);

  const companySelect = $(page.body).find("[data-company]");
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => {
    (r.message || []).forEach((row) => companySelect.append(`<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(row.name)}</option>`));
  });
  companySelect.on("change", refresh);
  $(page.body).find("[data-refresh]").on("click", refresh);

  function refresh() {
    const company = companySelect.val();
    if (!company || company === "Select Company") return;
    frappe.call({ method: "reckon_distribution.setup_guide.get_setup_status", args: { company } }).then((r) => render_steps(r.message));
  }

  function render_steps(status) {
    const steps = [
      { number: "1", title: "Company rules", bangla: "কোম্পানির নিয়ম", help: "Set supplier-goods policy, warehouse, accounts and payment defaults.", help_bn: "সরবরাহকারীর পণ্য, গুদাম, হিসাব ও পেমেন্টের নিয়ম ঠিক করুন।", done: status.settings > 0, route: "distribution-settings" },
      { number: "2", title: "Field user access", bangla: "ফিল্ড ব্যবহারকারী", help: "Create the SR/DSR login and give it access to this Company.", help_bn: "SR/DSR লগইন তৈরি করে এই কোম্পানির অ্যাক্সেস দিন।", done: status.users > 0, route: "user" },
      { number: "3", title: "Route", bangla: "রুট", help: "Create the route and assign the SR/DSR who works on it.", help_bn: "রুট তৈরি করে দায়িত্বপ্রাপ্ত SR/DSR নির্বাচন করুন।", done: status.routes > 0, route: "distribution-route" },
      { number: "4", title: "Retailer", bangla: "রিটেইলার", help: "Create the shop/customer record.", help_bn: "দোকান/কাস্টমার রেকর্ড তৈরি করুন।", done: status.retailers > 0, route: "customer" },
      { number: "5", title: "Retailer route", bangla: "রিটেইলার রুটে যুক্ত করুন", help: "Assign the retailer to the route and field user for today.", help_bn: "রিটেইলারকে আজকের রুট ও ফিল্ড ব্যবহারকারীর সাথে যুক্ত করুন।", done: status.assignments > 0, route: "retailer-route-assignment" },
      { number: "6", title: "Products and prices", bangla: "পণ্য ও দাম", help: "Enable products, price list and sales UOMs for this Company.", help_bn: "কোম্পানির জন্য পণ্য, মূল্য তালিকা ও বিক্রয় UOM চালু করুন।", done: status.products > 0 && status.prices > 0, route: "distribution-master-scope" },
      { number: "7", title: "Start field work", bangla: "ফিল্ড কাজ শুরু করুন", help: "Open the delivery page. Assigned retailers will appear here.", help_bn: "ডেলিভারি পেজ খুলুন। দায়িত্বপ্রাপ্ত রিটেইলার এখানে দেখা যাবে।", done: status.assignments > 0 && status.products > 0, route: "dsr-delivery" },
    ];
    $(page.body).find("[data-steps]").html(steps.map((step) => `<article class="rd-setup-step ${step.done ? "is-done" : ""}"><div class="rd-setup-number">${step.number}</div><div class="rd-setup-copy"><h3>${__(step.title)} <span>${__(step.bangla)}</span></h3><p>${__(step.help)}<br><small>${__(step.help_bn)}</small></p></div><div class="rd-setup-action">${step.done ? `<strong>${__("Done / সম্পন্ন")}</strong>` : ""}<a class="btn ${step.done ? "btn-default" : "btn-primary"}" href="${step.route === "dsr-delivery" ? "/desk/dsr-delivery" : `/app/${step.route}`}" >${step.done ? __("Review") : __("Open step")}</a></div></article>`).join(""));
  }
};
