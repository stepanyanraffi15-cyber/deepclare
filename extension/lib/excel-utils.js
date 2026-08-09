function goodsToExcelXlsx(declaration, goods) {
  const decl = declaration ?? {};
  const wb = XLSX.utils.book_new();

  // Sheet 1: declaration-level fields
  const declRows = [
    ["Հայտարարագրի տվյալներ", ""],
    ["Դեկլարանտ", decl.declarantName ?? ""],
    ["ՀՎՀՀ", decl.declarantUnn ?? ""],
    ["Լրացնող", decl.fillerName ?? ""],
    ["Ուղարկող (վաճառող)", decl.consignorName ?? ""],
    ["Ուղարկող երկիր", COUNTRY_NAME_BY_CODE[decl.senderCountry] ?? decl.senderCountry ?? ""],
    ["Առևտրի երկիր", decl.tradeCountry ?? ""],
    ["Incoterms", decl.incoterms ?? ""],
    ["Incoterms վայր", decl.incotermsPlace ?? ""],
    ["Արժույթ", decl.contractCurrency ?? ""],
    ["Ընդամենը գումար", decl.totalInvoiceAmount ?? ""],
    ["Փոխարժեք", decl.currencyRate ?? ""],
    ["Ապրանքային տողեր", decl.totalGoodsNumber ?? ""],
    ["Ընդամենը փաթեղ", decl.totalPackageNumber ?? ""],
    ["Մաքսային արժեքի որոշման մեթոդ", decl.customsMethod ?? ""],
  ];
  const ws1 = XLSX.utils.aoa_to_sheet(declRows);
  ws1["!cols"] = [{ wch: 28 }, { wch: 40 }];
  XLSX.utils.book_append_sheet(wb, ws1, "Հայտարարագիր");

  // Sheet 2: goods lines
  const goodsRows = [
    [
      "Տող",
      "Նկարագրություն",
      "ԱՏԳ ԱԱ կոդ",
      "Ծագման երկիր",
      "Քանակ",
      "Չափման միավոր",
      "Զուտ քաշ (կգ)",
      "Համախառն քաշ (կգ)",
      "Արժեք",
      "Փաթեթավորման ծածկագիր",
      "Փաթեթավորման կոդ",
    ],
    ...goods.map((item) => [
      item.numeric ?? "",
      item.description ?? "",
      item.tnvedCode ?? "",
      COUNTRY_NAME_BY_CODE[item.originCountry] ?? item.originCountry ?? "",
      item.quantity ?? "",
      item.quantityUnit ?? "",
      item.netWeight ?? "",
      item.grossWeight ?? "",
      item.invoicedCost ?? "",
      item.packageTypeCode ?? "",
      item.packingCode ?? "",
    ]),
  ];
  const ws2 = XLSX.utils.aoa_to_sheet(goodsRows);
  ws2["!cols"] = [
    { wch: 6 },
    { wch: 30 },
    { wch: 40 },
    { wch: 14 },
    { wch: 16 },
    { wch: 10 },
    { wch: 16 },
    { wch: 14 },
    { wch: 18 },
    { wch: 10 },
    { wch: 16 },
  ];
  XLSX.utils.book_append_sheet(wb, ws2, "Ապրանքներ");

  return XLSX.write(wb, { type: "array", bookType: "xlsx" });
}

function excelFilenameFrom(xmlFilename) {
  return xmlFilename.replace(/\.xml$/i, ".xlsx");
}
