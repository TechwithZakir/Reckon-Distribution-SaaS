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
      ["1", "Company rules", "কোম্পানির নিয়ম", "Set supplier-goods policy, warehouse, accounts and payment defaults.", "সরবরাহকারীর পণ্য, গুদাম, হিসাব ও পেমেন্টের নিয়ম ঠিক করুন।", status.settings > 0, "distribution-settings"],
      ["2", "Field user access", "ফিল্ড ব্যবহারকারী", "Create the SR/DSR login and give it access to this Company.", "SR/DSR লগইন তৈরি করে এই কোম্পানির অ্যাক্সেস দিন।", false, "user"],
      ["3", "Route", "রুট", "Create the route and assign the SR/DSR who works on it.", "রুট তৈরি করে দায়িত্বপ্রাপ্ত SR/DSR নির্বাচন করুন।", status.routes > 0, "distribution-route"],
      ["4", "Retailer", "রিটেইলার", "Create the shop/customer record.", "দোকান/কাস্টমার রেকর্ড তৈরি করুন।", status.retailers > 0, "customer"],
      ["5", "Retailer route", "রিটেইলার রুটে যুক্ত করুন", "Assign the retailer to the route and field user for today.", "রিটেইলারকে আজকের রুট ও ফিল্ড ব্যবহারকারীর সাথে যুক্ত করুন।", status.assignments > 0, "retailer-route-assignment"],
      ["6", "Products and prices", "পণ্য ও দাম", "Enable products, price list and sales UOMs for this Company.", "কোম্পানির জন্য পণ্য, মূল্য তালিকা ও বিক্রয় UOM চালু করুন।", status.products > 0 && status.prices > 0, "distribution-master-scope"],
      ["7", "Start field work", "ফিল্ড কাজ শুরু করুন", "Open the delivery page. Assigned retailers will appear here.", "ডেলিভারি পেজ খুলুন। দায়িত্বপ্রাপ্ত রিটেইলার এখানে দেখা যাবে।", status.assignments > 0 && status.products > 0, "dsr-delivery"],
    ];
    $(page.body).find("[data-steps]").html(steps.map((step) => `<article class="rd-setup-step ${step[6] ? "is-done" : ""}"><div class="rd-setup-number">${step[0]}</div><div class="rd-setup-copy"><h3>${__(step[1])} <span>${__(step[2])}</span></h3><p>${__(step[3])}<br><small>${__(step[4])}</small></p></div><div class="rd-setup-action">${step[6] ? `<strong>${__("Done / সম্পন্ন")}</strong>` : ""}<a class="btn ${step[6] ? "btn-default" : "btn-primary"}" href="${step[7] === "dsr-delivery" ? "/desk/dsr-delivery" : `/app/${step[7]}`}" >${step[6] ? __("Review") : __("Open step")}</a></div></article>`).join(""));
  }
};
