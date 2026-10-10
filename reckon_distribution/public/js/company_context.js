(() => {
  const doctypes = [
    "Tenant Security Test Record", "Purchase Receipt", "Purchase Order", "Purchase Invoice", "Payment Entry", "Delivery Note", "Stock Entry",
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

  function updateChallanTotals(frm) {
    let total = 0;
    (frm.doc.items || []).forEach(row => {
      row.total_price = row.stock_category === "Supplier Free"
        ? 0
        : flt(row.qty) * flt(row.unit_price);
      total += flt(row.total_price);
    });
    frm.doc.total_bill_amount = total;
    frm.refresh_field("items");
    frm.refresh_field("total_bill_amount");
  }

  frappe.ui.form.on("DSR Challan", {
    refresh: updateChallanTotals,
    validate: updateChallanTotals,
  });
  frappe.ui.form.on("DSR Challan Item", {
    qty: updateChallanTotals,
    unit_price: updateChallanTotals,
    stock_category: updateChallanTotals,
    item_code(frm, cdt, cdn) {
      loadChallanPrice(frm, cdt, cdn);
    },
    uom(frm, cdt, cdn) {
      loadChallanPrice(frm, cdt, cdn);
    },
  });

  function loadChallanPrice(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row || !row.item_code || !frm.doc.company) return;
    if (row.stock_category === "Supplier Free") {
      frappe.model.set_value(cdt, cdn, "unit_price", 0);
      updateChallanTotals(frm);
      return;
    }
    frappe.call({
      method: "reckon_distribution.van_loading.get_challan_item_price",
      args: {
        item_code: row.item_code,
        uom: row.uom,
        company: frm.doc.company,
      },
    }).then(result => {
      const message = result.message || {};
      if (message.price_list && frm.doc.price_list !== message.price_list) {
        frm.set_value("price_list", message.price_list);
      }
      if (!row.uom && message.uom) {
        frappe.model.set_value(cdt, cdn, "uom", message.uom);
      }
      frappe.model.set_value(cdt, cdn, "unit_price", message.unit_price || 0);
      updateChallanTotals(frm);
    });
  }
})();
