frappe.pages["van-loading"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Van Loading"),
    single_column: true,
  });

  $(page.body).html(`
    <div class="rd-van-loading">
      <section class="rd-van-loading__hero">
        <div><p class="rd-kicker">${__("Stock custody")}</p><h2>${__("Van Loading")}</h2><p>${__("Move approved saleable and supplier-free stock to an assigned DSR van with a traceable Stock Entry.")}</p></div>
        <a class="btn btn-primary" href="/desk/van-loading-challan/new-van-loading-challan-1">${__("New Loading Challan")}</a>
      </section>
      <section class="rd-van-loading__grid">
        ${tile("Manager queue", "Review, approve, cancel, and amend loading challans.", "van-loading-challan", "Open Challans")}
        ${tile("DSR acknowledgement", "Confirm accepted quantities and record partial rejections.", "van-loading-acknowledgement", "Open Acknowledgements")}
        ${tile("Stock custody", "Inspect the linked ERPNext Stock Entry created at approval.", "stock-entry", "Open Stock Entries")}
      </section>
      <div class="rd-van-loading__note"><strong>${__("Control rule")}</strong><span>${__("Approval creates one idempotent Material Transfer. Acknowledgement never changes the original loaded quantity; rejected quantities remain visible for later return handling.")}</span></div>
    </div>
  `);

  function tile(title, description, route, action) {
    return `<a class="rd-van-tile" href="/desk/${route}"><span class="rd-van-tile__icon">${title.charAt(0)}</span><span><strong>${__(title)}</strong><small>${__(description)}</small><em>${__(action)} &rarr;</em></span></a>`;
  }
};
