frappe.pages["distribution-item-uom-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Item Units & Conversion"), single_column: true });
  $(page.body).html(`<div class="rd-uom-setup"><h2>${__("Item units & conversion / পণ্যের ইউনিট ও রূপান্তর")}</h2><p class="text-muted">${__("Choose an item and define how many stock units are in each sales unit. UOM definitions are shared and read-only. / পণ্য নির্বাচন করে বিক্রয় ইউনিটে কত স্টক ইউনিট আছে তা দিন। UOM সংজ্ঞা সবার জন্য এক এবং শুধু পড়া যাবে।")}</p><label>${__("Product / পণ্য")}<select data-item><option value="">${__("Select product")}</option></select></label><div data-editor></div></div>`);
  const itemSelect = $(page.body).find("[data-item]");
  let state = {};
  load();
  itemSelect.on("change", () => load(itemSelect.val()));

  function load(item) {
    frappe.call({ method: "reckon_distribution.setup_guide.get_setup_companies" }).then((companies) => {
      const company = (companies.message || [])[0]?.name;
      if (!company) return;
      return frappe.call({ method: "reckon_distribution.uom_setup.get_uom_setup", args: { company, item } });
    }).then((response) => {
      if (!response) return;
      state = response.message || {};
      if (!item) itemSelect.html(`<option value="">${__("Select product")}</option>${(state.items || []).map((row) => `<option value="${esc(row.name)}">${esc(row.item_name)}</option>`).join("")}`);
      render();
    });
  }

  function render() {
    const selected = state.item;
    if (!selected) { $(page.body).find("[data-editor]").html(`<p class="text-muted">${__("Select a product to continue. / শুরু করতে একটি পণ্য নির্বাচন করুন।")}</p>`); return; }
    const rows = selected.uoms || [];
    $(page.body).find("[data-editor]").html(`<div class="rd-uom-stock"><strong>${__("Stock unit / স্টক ইউনিট")}</strong><span>${esc(selected.stock_uom)}</span></div><p>${__("Example: 1 Carton = 24 Nos. / উদাহরণ: ১ কার্টন = ২৪ পিস।")}</p><div data-rows>${rows.map(row_html).join("")}</div><button class="btn btn-default" data-add>${__("Add sales unit / বিক্রয় ইউনিট যোগ করুন")}</button> <button class="btn btn-primary" data-save>${__("Save conversion / রূপান্তর সংরক্ষণ")}</button>`);
    $(page.body).find("[data-add]").on("click", () => { $(page.body).find("[data-rows]").append(row_html({})); });
    $(page.body).find("[data-save]").on("click", save);
  }

  function row_html(row) {
    return `<div class="rd-uom-row"><select data-uom><option value="">${__("Select UOM")}</option>${(state.units || []).filter((uom) => uom !== state.item.stock_uom).map((uom) => `<option ${uom === row.uom ? "selected" : ""}>${esc(uom)}</option>`).join("")}</select><input data-factor type="number" min="0.000001" step="0.000001" value="${esc(row.conversion_factor || "")}" placeholder="${__("Stock units")}" /><button class="btn btn-link text-danger" data-remove aria-label="${__("Remove")}">×</button></div>`;
  }

  function save() {
    const rows = $(page.body).find("[data-rows] .rd-uom-row").map(function () { return { uom: $(this).find("[data-uom]").val(), conversion_factor: $(this).find("[data-factor]").val() }; }).get();
    frappe.call({ method: "reckon_distribution.uom_setup.save_uom_setup", args: { company: state.company, item: state.item.name, rows: JSON.stringify(rows) } }).then(() => { frappe.show_alert({ message: __("Saved / সংরক্ষণ হয়েছে"), indicator: "green" }); load(state.item.name); });
  }
  $(page.body).on("click", "[data-remove]", function () { $(this).closest(".rd-uom-row").remove(); });
  function esc(value) { return frappe.utils.escape_html(String(value == null ? "" : value)); }
};
