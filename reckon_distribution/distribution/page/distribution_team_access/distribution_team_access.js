frappe.pages["distribution-team-access"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Company Team & Access"), single_column: true });
  $(page.body).html(`<main class="rd-team-access"><section class="rd-team-hero"><p class="rd-kicker">${__("People and permissions / মানুষ ও অনুমতি")}</p><h2>${__("Company Team & Access")}</h2><p>${__("Add a field user, choose what they do, and keep their data inside this Company. / ফিল্ড ব্যবহারকারী যোগ করুন, দায়িত্ব নির্বাচন করুন এবং এই কোম্পানির ডেটার মধ্যে সীমাবদ্ধ রাখুন।")}</p></section><section class="rd-team-card"><label>${__("Company / কোম্পানি")}<select data-company><option>${__("Select Company")}</option></select></label></section><section class="rd-team-card"><h3>${__("Add a team member / টিম সদস্য যোগ করুন")}</h3><div class="rd-team-form"><label>${__("Full name / পূর্ণ নাম")}<input data-name placeholder="${__("Example: Rahim Uddin")}" /></label><label>${__("Email / ইমেইল")}<input data-email type="email" placeholder="name@example.com" /></label><label>${__("Password / পাসওয়ার্ড")}<input data-password type="password" autocomplete="new-password" placeholder="${__("At least 8 characters")}" /></label><label>${__("Confirm password / পাসওয়ার্ড নিশ্চিত করুন")}<input data-password-confirm type="password" autocomplete="new-password" /></label><label>${__("Role / দায়িত্ব")}<select data-role><option value="DSR">DSR - ${__("Deliver and collect")}</option><option value="SR">SR - ${__("Take orders")}</option><option value="Company Manager">${__("Company Manager")}</option><option value="Master Data Manager">${__("Master Data Manager")}</option></select></label><label>${__("Route (optional) / রুট (ঐচ্ছিক)")}<select data-route><option value="">${__("All assigned routes / সব নির্ধারিত রুট")}</option></select></label><button class="btn btn-primary" data-add>${__("Add access / অ্যাক্সেস দিন")}</button></div><p class="text-muted" data-message>${__("For an existing member, leave both password fields empty to keep the current password. / পুরনো সদস্যের পাসওয়ার্ড অপরিবর্তিত রাখতে দুটি ঘর খালি রাখুন।")}</p></section><section class="rd-team-card"><h3>${__("Active team / সক্রিয় টিম")}</h3><div data-team><p class="text-muted">${__("Loading...")}</p></div></section></main>`);
  const message = $(page.body).find("[data-message]");
  const company = $(page.body).find("[data-company]");
  $(page.body).find("[data-add]").on("click", addMember);
  company.on("change", loadTeam);
  frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((r) => { (r.message || []).forEach((row) => company.append(`<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(row.name)}</option>`)); if ((r.message || []).length === 1) { company.val(r.message[0].name); loadTeam(); } });

  function loadTeam() {
    if (!company.val() || company.val() === "Select Company") return;
    Promise.all([
      frappe.call({ method: "reckon_distribution.setup_guide.get_setup_links", args: { company: company.val() } }),
      frappe.call({ method: "reckon_distribution.team_access.list_team", args: { company: company.val() } }),
    ]).then(([linkResponse, r]) => {
      const routeSelect = $(page.body).find("[data-route]").empty().append(`<option value="">${__("All assigned routes / সব নির্ধারিত রুট")}</option>`);
      (linkResponse.message.routes || []).forEach((route) => routeSelect.append(`<option value="${frappe.utils.escape_html(route.name)}">${frappe.utils.escape_html(route.route_name || route.name)}</option>`));
      const rows = r.message || [];
      $(page.body).find("[data-team]").html(rows.length ? rows.map((row) => `<div class="rd-team-row"><strong>${frappe.utils.escape_html(row.user)}</strong><span>${frappe.utils.escape_html(row.role_profile || "")}</span><em>${row.active ? __("Active") : __("Inactive")}</em><button class="btn btn-default btn-xs" data-edit-team='${JSON.stringify(row)}'>${__("Edit")}</button>${row.active ? `<button class="btn btn-default btn-xs" data-reset-password="${row.name}">${__("Send password link / পাসওয়ার্ড লিংক")}</button><button class="btn btn-danger btn-xs" data-disable-team="${row.name}">${__("Deactivate")}</button>` : ""}</div>`).join("") : `<p class="text-muted">${__("No team members added yet.")}</p>`);
      $(page.body).find("[data-edit-team]").on("click", function () { const row = JSON.parse($(this).attr("data-edit-team")); $(page.body).find("[data-email]").val(row.user); $(page.body).find("[data-password], [data-password-confirm]").val(""); $(page.body).find("[data-role]").val(row.role_profile); $(page.body).find("[data-route]").val(row.route_scope || ""); $(page.body).find("[data-add]").data("editing", row.name).text(__("Save changes")); });
      $(page.body).find("[data-disable-team]").on("click", function () { frappe.call({ method: "reckon_distribution.team_access.deactivate_team_access", args: { assignment: $(this).data("disable-team") } }).then(loadTeam); });
    });
  }

  function addMember() {
    const payload = { company: company.val(), full_name: $(page.body).find("[data-name]").val(), email: $(page.body).find("[data-email]").val(), password: $(page.body).find("[data-password]").val(), password_confirm: $(page.body).find("[data-password-confirm]").val(), role_profile: $(page.body).find("[data-role]").val(), route: $(page.body).find("[data-route]").val() };
    const editing = $(page.body).find("[data-add]").data("editing");
    payload.name = editing;
    const method = editing ? "reckon_distribution.team_access.update_team_access" : "reckon_distribution.team_access.create_team_access";
    frappe.call({ method, args: { payload: JSON.stringify(payload) } }).then((r) => { message.text(__("Access saved: {0}", [r.message])); $(page.body).find("[data-password], [data-password-confirm]").val(""); $(page.body).find("[data-add]").removeData("editing").text(__("Add access / অ্যাক্সেস দিন")); loadTeam(); }).catch(() => message.text(__("Could not save access. Check the fields and your Company role.")));
  }
};
