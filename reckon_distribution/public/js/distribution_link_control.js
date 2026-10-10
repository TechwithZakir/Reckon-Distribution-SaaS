/* Link controls for Distribution custom pages only. */
window.reckonDistribution = window.reckonDistribution || {};
window.reckonDistribution.makeLinkControl = function (parent, fieldname, label, options) {
  const control = frappe.ui.form.make_control({
    parent,
    df: { fieldname, fieldtype: "Link", label, options },
    render_input: true,
  });
  control.refresh();
  return control;
};
