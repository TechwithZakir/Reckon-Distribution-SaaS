frappe.ui.form.on("Office Expense", {
  refresh(frm) {
    loadOfficeExpenseChoices(frm);
    updateOfficeExpenseTotal(frm);
  },
  company(frm) {
    loadOfficeExpenseChoices(frm);
  },
  validate(frm) {
    updateOfficeExpenseTotal(frm);
  },
});

frappe.ui.form.on("Office Expense Item", {
  amount(frm) {
    updateOfficeExpenseTotal(frm);
  },
});

function loadOfficeExpenseChoices(frm) {
  if (frm.__officeExpenseChoicesLoading || frm.__officeExpenseChoicesLoaded) return;
  frm.__officeExpenseChoicesLoading = true;
  frappe.call({ method: "reckon_distribution.office_expense.get_office_expense_defaults" })
    .then((response) => {
      const settings = response.message || {};
      if (!settings.configured) {
        frm.set_intro(
          __("Office Expense Setup is required before an expense can be submitted."),
          "orange"
        );
        return;
      }
      frm.__officeExpenseChoicesLoaded = true;
      frm.set_df_property("payment_method", "options", settings.payment_methods.join("\n"));
      frm.fields_dict.items.grid.update_docfield_property(
        "expense_category",
        "options",
        settings.categories.join("\n")
      );
      if (!frm.doc.payment_method) frm.set_value("payment_method", settings.default_payment_method);
      if (frm.is_new() && !frm.doc.items.length) {
        const row = frm.add_child("items");
        row.expense_category = settings.default_expense_category;
        frm.refresh_field("items");
      }
    })
    .finally(() => {
      frm.__officeExpenseChoicesLoading = false;
    });
}

function updateOfficeExpenseTotal(frm) {
  const total = (frm.doc.items || []).reduce((sum, row) => sum + flt(row.amount), 0);
  frm.doc.total_amount = total;
  frm.refresh_field("total_amount");
}
