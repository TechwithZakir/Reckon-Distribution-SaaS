frappe.pages["van-loading"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Van Loading / ভ্যান লোডিং"),
    single_column: true,
  });

  $(page.body).html(`
    <div class="rd-van-loading">
      <section class="rd-van-loading__hero">
        <div><p class="rd-kicker">${__("Prepare and hand over stock / পণ্য প্রস্তুত ও হস্তান্তর")}</p><h2>${__("Van Loading / ভ্যান লোডিং")}</h2><p>${__("A manager prepares the van load; the DSR receives it. Stock posting happens automatically in the background.")}</p></div>
        <a class="btn btn-primary" href="/desk/van-loading-challan/new-van-loading-challan-1">${__("Create loading request")}</a>
      </section>
      <section class="rd-van-loading__grid">
        ${tile("Loading requests / লোডিং অনুরোধ", "Manager reviews, approves, cancels, or amends a van load.", "van-loading-challan", "Review requests")}
        ${tile("Receive van load / ভ্যান লোড গ্রহণ", "DSR confirms accepted quantities and records partial rejection.", "van-loading-acknowledgement", "Receive load")}
      </section>
      <div class="rd-van-loading__note"><strong>${__("How it works")}</strong><span>${__("Approval automatically creates one ERPNext stock transfer. Users do not need to open Stock Entry. Acknowledgement never changes the original loaded quantity; rejected quantities remain visible for later return handling.")}</span></div>
    </div>
  `);

  function tile(title, description, route, action) {
    return `<a class="rd-van-tile" href="/desk/${route}"><span class="rd-van-tile__icon">${title.charAt(0)}</span><span><strong>${__(title)}</strong><small>${__(description)}</small><em>${__(action)} &rarr;</em></span></a>`;
  }
};
