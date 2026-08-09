// Working on-page imitation of the DeepClare extension side panel: the whole UI
// is clickable — file upload (real files or the sample documents), run options,
// the real pipeline stepper, menu with history/account/feedback, a full goods
// editor and real XML/CSV downloads built from the edited fields. No network
// calls, no real processing: the result is always the sample data.

(function () {
  "use strict";

  var panel = document.getElementById("try-panel");
  if (!panel) return;

  var $ = function (id) {
    return document.getElementById(id);
  };
  var flow = $("try-flow");
  var drop = $("try-drop");
  var filesInput = $("try-files");
  var chips = $("try-chips");
  var actionBtn = $("try-action");
  var progressBox = $("try-progress-box");
  var progressStatus = $("try-progress-status");
  var progressFill = $("try-progress");
  var stages = Array.prototype.slice.call(progressBox.querySelectorAll(".demo-stage"));
  var result = $("try-result");
  var goodsList = $("try-goods-list");
  var toast = $("try-toast");
  var timers = [];

  var STAGE_STATUS = [
    "Փաստաթղթերը կարդացվում են…",
    "Անվանումները թարգմանվում են…",
    "ԱՏԳ կոդերը որոշվում են…",
    "Հայտարարագիրը կազմվում է…",
  ];

  var FIELDS = [
    { key: "description", label: "Ապրանքի նկարագրություն", span: true },
    { key: "tnvedCode", label: "ԱՏԳ ԱԱ կոդ", atg: true },
    { key: "quantity", label: "Քանակ" },
    { key: "quantityUnit", label: "Չափման միավոր" },
    { key: "netWeight", label: "Զուտ քաշ (կգ)" },
    { key: "grossWeight", label: "Համախառն քաշ (կգ)" },
    { key: "invoicedCost", label: "Ֆակտուրային արժեք" },
    { key: "originCountry", label: "Ծագման երկիր" },
    { key: "packageQuantity", label: "Փաթեթների քանակ" },
    { key: "packageTypeCode", label: "Փաթեթի տեսակի կոդ" },
  ];

  var SAMPLE_GOODS = [
    { description: "Սմարթֆոն Samsung Galaxy A15", tnvedCode: "8517130000", quantity: "50", quantityUnit: "հատ", netWeight: "22,0", grossWeight: "24,5", invoicedCost: "6 500", originCountry: "Չինաստան", packageQuantity: "5", packageTypeCode: "CT" },
    { description: "Անվադող մարդատար՝ 205/55 R16", tnvedCode: "4011100003", quantity: "120", quantityUnit: "հատ", netWeight: "950", grossWeight: "986", invoicedCost: "4 730", originCountry: "Լեհաստան", packageQuantity: "30", packageTypeCode: "PX" },
    { description: "Սուրճ աղացած, բովված", tnvedCode: "", quantity: "500", quantityUnit: "կգ", netWeight: "500", grossWeight: "749,5", invoicedCost: "1 250", originCountry: "Բրազիլիա", packageQuantity: "25", packageTypeCode: "BG" },
  ];
  var ATG_FOUND = "0901210001";

  function later(fn, ms) {
    timers.push(window.setTimeout(fn, ms));
  }
  function clearTimers() {
    timers.forEach(window.clearTimeout);
    timers = [];
  }
  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    later(function () {
      toast.hidden = true;
    }, 2400);
  }
  function flashStatus(el) {
    el.hidden = false;
    later(function () {
      el.hidden = true;
    }, 2200);
  }

  // ---- intake: real files, sample documents, drag & drop ----

  var fileCount = 0;

  function addChip(name) {
    var chip = document.createElement("span");
    chip.className = "file-chip";
    chip.textContent = "📄 " + name;
    chips.appendChild(chip);
    chips.hidden = false;
    fileCount += 1;
    actionBtn.disabled = false;
    drop.classList.add("has-files");
  }

  var sampleAdded = {};
  var SAMPLE_FILES = { invoice: "invoice_0417.pdf", cmr: "CMR_7715.pdf" };

  function addSampleDoc(kind) {
    if (!SAMPLE_FILES[kind] || sampleAdded[kind]) return;
    sampleAdded[kind] = true;
    addChip(SAMPLE_FILES[kind]);
    var card = document.querySelector('.doc-card[data-doc="' + kind + '"]');
    if (card) card.classList.add("added");
  }

  filesInput.addEventListener("change", function () {
    Array.prototype.slice.call(filesInput.files).forEach(function (file) {
      addChip(file.name);
    });
    filesInput.value = "";
  });

  Array.prototype.slice.call(document.querySelectorAll(".doc-card")).forEach(function (card) {
    card.addEventListener("click", function () {
      addSampleDoc(card.dataset.doc);
    });
    card.addEventListener("dragstart", function (event) {
      event.dataTransfer.setData("text/plain", card.dataset.doc);
      event.dataTransfer.effectAllowed = "copy";
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", function () {
      card.classList.remove("dragging");
    });
  });

  [drop, panel].forEach(function (target) {
    target.addEventListener("dragover", function (event) {
      event.preventDefault();
      drop.classList.add("drag-over");
    });
    target.addEventListener("dragleave", function () {
      drop.classList.remove("drag-over");
    });
    target.addEventListener("drop", function (event) {
      event.preventDefault();
      drop.classList.remove("drag-over");
      var kind = event.dataTransfer.getData("text/plain");
      if (kind) addSampleDoc(kind);
    });
  });

  // ---- run options ----

  $("try-example-toggle").addEventListener("change", function () {
    $("try-example-body").hidden = !this.checked;
  });
  $("try-example-zone").addEventListener("click", function () {
    $("try-example-chip").hidden = false;
    this.hidden = true;
  });

  // ---- pipeline run ----

  actionBtn.addEventListener("click", function () {
    actionBtn.disabled = true;
    actionBtn.textContent = "Մշակվում է…";
    progressBox.hidden = false;
    stages.forEach(function (li) {
      li.classList.remove("running", "done");
    });
    progressFill.style.width = "0%";
    stages.forEach(function (li, i) {
      later(function () {
        li.classList.add("running");
        progressStatus.textContent = STAGE_STATUS[i];
        progressFill.style.width = String(Math.round(((i + 0.5) / stages.length) * 100)) + "%";
      }, i * 1050);
      later(function () {
        li.classList.remove("running");
        li.classList.add("done");
        progressFill.style.width = String(Math.round(((i + 1) / stages.length) * 100)) + "%";
      }, i * 1050 + 950);
    });
    later(showResult, stages.length * 1050 + 400);
  });

  function showResult() {
    progressStatus.textContent = "Պատրաստ է";
    result.hidden = false;
    $("try-new").hidden = false;
    actionBtn.hidden = true;
    renderGoods();
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ---- goods editor ----

  function fieldRow(field, value) {
    var label = document.createElement("label");
    label.className = "ext-field" + (field.span ? " span-2" : "");
    var caption = document.createElement("span");
    caption.textContent = field.label;
    var input = document.createElement("input");
    input.value = value || "";
    input.dataset.field = field.key;
    input.addEventListener("input", function () {
      input.classList.toggle("is-empty", !input.value.trim());
    });
    input.classList.toggle("is-empty", !(value || "").trim());
    label.appendChild(caption);
    label.appendChild(input);
    if (field.atg && !(value || "").trim()) {
      var atgBtn = document.createElement("button");
      atgBtn.type = "button";
      atgBtn.className = "atg-btn";
      atgBtn.textContent = "Որոնել ԱՏԳ";
      atgBtn.addEventListener("click", function () {
        atgBtn.textContent = "Որոնվում է…";
        atgBtn.disabled = true;
        later(function () {
          input.value = ATG_FOUND;
          input.classList.remove("is-empty");
          input.dispatchEvent(new Event("input"));
          atgBtn.textContent = "Կատարվեց";
          later(function () {
            atgBtn.remove();
          }, 900);
        }, 1300);
      });
      label.appendChild(atgBtn);
    }
    return label;
  }

  function goodsCard(item, index, open) {
    var card = document.createElement("div");
    card.className = "goods-card" + (open ? " open" : "");

    var summary = document.createElement("button");
    summary.type = "button";
    summary.className = "goods-summary";
    var num = document.createElement("span");
    num.className = "goods-num";
    num.textContent = String(index + 1);
    var sumDesc = document.createElement("span");
    sumDesc.className = "goods-sum-desc";
    sumDesc.textContent = item.description || "Նոր ապրանք";
    var sumCode = document.createElement("span");
    sumCode.className = "goods-sum-code" + (item.tnvedCode ? "" : " is-empty");
    sumCode.textContent = item.tnvedCode || "առանց կոդի";
    var chevron = document.createElement("span");
    chevron.className = "goods-chevron";
    chevron.textContent = "▾";
    summary.append(num, sumDesc, sumCode, chevron);
    summary.addEventListener("click", function () {
      card.classList.toggle("open");
    });

    var grid = document.createElement("div");
    grid.className = "goods-fields ext-field-grid";
    FIELDS.forEach(function (field) {
      grid.appendChild(fieldRow(field, item[field.key]));
    });
    grid.addEventListener("input", function (event) {
      var key = event.target.dataset.field;
      if (key === "description") sumDesc.textContent = event.target.value || "Նոր ապրանք";
      if (key === "tnvedCode") {
        sumCode.textContent = event.target.value || "առանց կոդի";
        sumCode.classList.toggle("is-empty", !event.target.value.trim());
      }
    });

    card.appendChild(summary);
    card.appendChild(grid);
    return card;
  }

  function renderGoods() {
    goodsList.innerHTML = "";
    SAMPLE_GOODS.forEach(function (item, i) {
      goodsList.appendChild(goodsCard(item, i, i === 0));
    });
  }

  $("try-add-goods").addEventListener("click", function () {
    var blank = {};
    FIELDS.forEach(function (field) {
      blank[field.key] = "";
    });
    var card = goodsCard(blank, goodsList.children.length, true);
    goodsList.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  function collectGoods() {
    return Array.prototype.slice.call(goodsList.querySelectorAll(".goods-card")).map(function (card) {
      var item = {};
      Array.prototype.slice.call(card.querySelectorAll("input[data-field]")).forEach(function (input) {
        item[input.dataset.field] = input.value;
      });
      return item;
    });
  }

  function download(name, mime, content) {
    var blob = new Blob([content], { type: mime });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  $("try-download").addEventListener("click", function () {
    var goods = collectGoods()
      .map(function (item, i) {
        return (
          "  <ESADout_CUGoods>\n" +
          "    <GoodsNumeric>" + (i + 1) + "</GoodsNumeric>\n" +
          "    <GoodsDescription>" + item.description + "</GoodsDescription>\n" +
          "    <GoodsTNVEDCode>" + item.tnvedCode + "</GoodsTNVEDCode>\n" +
          "    <GoodsQuantity>" + item.quantity + "</GoodsQuantity>\n" +
          "    <SupplementaryQuantityUnit>" + item.quantityUnit + "</SupplementaryQuantityUnit>\n" +
          "    <NetWeightQuantity>" + item.netWeight + "</NetWeightQuantity>\n" +
          "    <GrossWeightQuantity>" + item.grossWeight + "</GrossWeightQuantity>\n" +
          "    <InvoicedCost>" + item.invoicedCost + "</InvoicedCost>\n" +
          "    <OriginCountryName>" + item.originCountry + "</OriginCountryName>\n" +
          "    <PakageQuantity>" + item.packageQuantity + "</PakageQuantity>\n" +
          "    <PakageTypeCode>" + item.packageTypeCode + "</PakageTypeCode>\n" +
          "  </ESADout_CUGoods>"
        );
      })
      .join("\n");
    var xml =
      '<?xml version="1.0" encoding="UTF-8"?>\n' +
      "<!-- Օրինակելի ֆայլ. ստեղծված է deepclare.am կայքի փորձնական վահանակում -->\n" +
      "<ESADout_CU>\n" + goods + "\n</ESADout_CU>\n";
    download("ESADout_CU_orinak.xml", "application/xml", xml);
    showToast("ESADout_CU ֆայլը ներբեռնվեց");
  });

  $("try-excel").addEventListener("click", function () {
    var header = FIELDS.map(function (field) {
      return '"' + field.label + '"';
    }).join(",");
    var rows = collectGoods().map(function (item) {
      return FIELDS.map(function (field) {
        return '"' + String(item[field.key] || "").replace(/"/g, '""') + '"';
      }).join(",");
    });
    download("ESADout_CU_orinak.csv", "text/csv;charset=utf-8", "﻿" + [header].concat(rows).join("\n"));
    showToast("Աղյուսակը ներբեռնվեց (CSV)");
  });

  $("try-save").addEventListener("click", function () {
    flashStatus($("try-save-status"));
  });
  $("try-feedback-send").addEventListener("click", function () {
    $("try-feedback-input").value = "";
    flashStatus($("try-feedback-status"));
  });

  // ---- header: new declaration, menu, overlays ----

  function resetAll() {
    clearTimers();
    fileCount = 0;
    sampleAdded = {};
    chips.innerHTML = "";
    chips.hidden = true;
    drop.classList.remove("has-files");
    actionBtn.hidden = false;
    actionBtn.disabled = true;
    actionBtn.textContent = "Սկսել";
    progressBox.hidden = true;
    result.hidden = true;
    $("try-new").hidden = true;
    Array.prototype.slice.call(document.querySelectorAll(".doc-card.added")).forEach(function (card) {
      card.classList.remove("added");
    });
  }

  $("try-new").addEventListener("click", resetAll);

  var menu = $("try-menu");
  $("try-menu-btn").addEventListener("click", function (event) {
    event.stopPropagation();
    menu.hidden = !menu.hidden;
  });
  document.addEventListener("click", function () {
    menu.hidden = true;
  });

  var overlays = {
    history: $("try-overlay-history"),
    account: $("try-overlay-account"),
    contact: $("try-overlay-contact"),
  };
  function closeOverlays() {
    Object.keys(overlays).forEach(function (key) {
      overlays[key].hidden = true;
    });
    flow.hidden = false;
  }
  Array.prototype.slice.call(menu.querySelectorAll(".ext-dropdown-item")).forEach(function (item) {
    item.addEventListener("click", function () {
      menu.hidden = true;
      var target = item.dataset.menu;
      if (target === "logout") {
        showToast("Փորձնական տարբերակ․ ելքն անջատված է");
        return;
      }
      closeOverlays();
      flow.hidden = true;
      overlays[target].hidden = false;
    });
  });
  Array.prototype.slice.call(panel.querySelectorAll("[data-back]")).forEach(function (btn) {
    btn.addEventListener("click", closeOverlays);
  });
  Array.prototype.slice.call(panel.querySelectorAll("[data-history]")).forEach(function (entry) {
    entry.addEventListener("click", function () {
      closeOverlays();
      if (result.hidden) {
        addSampleDoc("invoice");
        progressBox.hidden = true;
        showResult();
      }
      showToast("Բեռնված է պատմությունից");
    });
  });
  $("try-account-save").addEventListener("click", function () {
    flashStatus($("try-account-status"));
  });
  $("try-contact-send").addEventListener("click", function () {
    $("try-contact-input").value = "";
    flashStatus($("try-contact-status"));
  });

  // Verification hook: ?autoplay=1 feeds the samples and starts the run.
  if (new URLSearchParams(window.location.search).has("autoplay")) {
    later(function () {
      addSampleDoc("invoice");
      addSampleDoc("cmr");
      actionBtn.click();
    }, 300);
  }
})();
