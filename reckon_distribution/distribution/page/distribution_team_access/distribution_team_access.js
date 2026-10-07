frappe.pages["distribution-team-access"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Company Team & Access"), single_column: true });
  $(page.body).html(`<main class="rd-team-access"><section class="rd-team-hero"><p class="rd-kicker">${__("People and permissions / মানুষ ও অনুমতি")}</p><h2>${__("Company Team & Access")}</h2><p>${__("Add a field user, choose what they do, and keep their data inside this Company. / ফিল্ড ব্যবহারকারী যোগ করুন, দায়িত্ব নির্বাচন করুন এবং এই কোম্পানির ডেটার মধ্যে সীমাবদ্ধ রাখুন।")}</p></section><section class="rd-team-card"><label>${__("Company / কোম্পানি")}<select data-company><option>${__("Select Company")}</option></select></label></section><section class="rd-team-card"><h3>${__("Add a team member / টিম সদস্য যোগ করুন")}</h3><div class="rd-team-form"><label>${__("Full name / পূর্ণ নাম")}<input data-name placeholder="${__("Example: Rahim Uddin")}" /></label><label>${__("Email / ইমেইল")}<input data-email type="email" placeholder="name@example.com" /></label><label>${__("Role / দায়িত্ব")}<select data-role><option value="DSR">DSR - ${__("Deliver and collect")}</option><option value="SR">SR - ${__("Take orders")}</option><option value="Company Manager">${__("Company Manager")}</option><option value="Master Data Manager">${__("Master Data Manager")}</option></select></label><label>${__("Route (optional) / রুট (ঐচ্ছিক)")}<input data-route placeholder="${__("Choose later in route setup")}" /></label><button class="btn btn-primary" data-add>${__("Add access / অ্যাক্সেস দিন")}</button></div><p class="text-muted" data-message>${__("The user will see only assigned Company work. / ব্যবহারকারী শুধু নির্ধারিত কোম্পানির কাজ দেখতে পাবেন।")}</p></section><section class="rd-team-card"><h3>${__("Active team / সক্রিয় টিম")}</h3><div data-team><p class="text-muted">${__("Loading...")}</p></div></section></main>`);
  const message = $(page.body).find("[data-message]");
  const company = $(page.body).find("[data-company]");
  $(page.body).find("[data-add]").on("click", addMember);
  company.on("change", loadTeam);
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => { (r.message || []).forEach((row) => company.append(`<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(row.name)}</option>`)); if ((r.message || []).length === 1) { company.val(r.message[0].name); loadTeam(); } });

  function loadTeam() {
    if (!company.val() || company.val() === "Select Company") return;
    frappe.call({ method: "reckon_distribution.team_access.list_team", args: { company: company.val() } }).then((r) => {
      const rows = r.message || [];
      $(page.body).find("[data-team]").html(rows.length ? rows.map((row) => `<div class="rd-team-row"><strong>${frappe.utils.escape_html(row.user)}</strong><span>${frappe.utils.escape_html(row.role_profile || "")}</span><em>${row.active ? __("Active") : __("Inactive")}</em></div>`).join("") : `<p class="text-muted">${__("No team members added yet.")}</p>`);
    });
  }

  function addMember() {
    const payload = { company: company.val(), full_name: $(page.body).find("[data-name]").val(), email: $(page.body).find("[data-email]").val(), role_profile: $(page.body).find("[data-role]").val(), route: $(page.body).find("[data-route]").val() };
    frappe.call({ method: "reckon_distribution.team_access.create_team_access", args: { payload: JSON.stringify(payload) } }).then((r) => { message.text(__("Access created: {0}", [r.message])); loadTeam(); }).catch(() => message.text(__("Could not create access. Check the fields and your Company role.")));
  }
};
