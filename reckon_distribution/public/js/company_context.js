(() => {
  const doctypes = [
    "Tenant Security Test Record", "Purchase Receipt", "Delivery Note", "Stock Entry",
    "DSR Challan", "Van Loading Acknowledgement", "DSR Collection Receipt",
    "DSR Due Assignment", "Retailer Route Assignment", "Outlet Visit", "SR Order",
    "Return Inspection", "DSR Day Settlement", "Distribution Settings", "Company UOM Profile",
    "Distribution Route", "Distribution Master Scope", "Warehouse", "Customer", "Supplier",
    "Item", "Item Price", "Price List",
  ];
  frappe.reckon_distribution = frappe.reckon_distribution || {};
  const state = frappe.reckon_distribution;
  if (state.company_forms_registered) return;
  state.company_forms_registered = true;

  async function applyCompany(frm) {
    if (frappe.session.user === "Administrator" ||
        ["System Manager", "Reckon Vendor Superuser"].some(role => frappe.user_roles.includes(role))) return;
    const fields = ["company", "rd_company"].filter(name => frm.fields_dict[name]);
    if (!fields.length) return;
    fields.forEach(name => {
      frm.set_df_property(name, "hidden", 1);
      frm.set_df_property(name, "read_only", 1);
    });
    if (!state.company_context) {
      state.company_context = frappe.call({
        method: "reckon_distribution.company_context.get_form_company",
      }).then(r => r.message).catch(error => {
        state.company_context = null;
        throw error;
      });
    }
    const context = await state.company_context;
    if (!context.restricted || !frm.is_new()) return;
    for (const name of fields) {
      if (frm.doc[name] !== context.company) await frm.set_value(name, context.company);
    }
  }
  doctypes.forEach(doctype => frappe.ui.form.on(doctype, {
    onload: applyCompany,
    refresh: applyCompany,
  }));
})();
