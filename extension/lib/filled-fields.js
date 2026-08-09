// Fields DeepClare fills in ESADout_CU (see docs/XML_FIELD_MAPPING.md). Omitted portal fields
// (RegNumberDoc, payments, …) and deferred slots (FilledPerson) are not shown here.

const PLACEHOLDER = "-";

// Transport mode codes offered in the border/arrival dropdowns (ADR-0024). The renderer
// defaults both to 31 (road); the user may switch to 30.
const TRANSPORT_MODE_OPTIONS = [
  { value: "30", label: "30" },
  { value: "31", label: "31" },
];

// Packaging classifier (field 20) — the tax-gov 0/1/2 values (ADR-0024).
const PACKAGE_TYPE_OPTIONS = [
  { value: "0", label: "0 — Առանց փաթեթավորման" },
  { value: "1", label: "1 — Փաթեթավորված" },
  { value: "2", label: "2 — Առանց փաթեթ. (տրանսպ. սարքավորված տարաներ)" },
];

// Customs-value determination method (box 43). One method per DECLARATION — it is identical
// across every goods line — so it is chosen once on the general card and fanned out to all goods
// on write-back (xml-utils.updateDeclarationInXml). Full method list (tax-gov 0-6).
const CUSTOMS_METHOD_OPTIONS = [
  { value: "0", label: "0 — Մաքսային արժեքի հետաձգված կարգով որոշում" },
  { value: "1", label: "1 — Ներմուծվող ապրանքների գործարքի արժեքի մեթոդ" },
  { value: "2", label: "2 — Նույնական ապրանքների գործարքի գնի որոշման մեթոդ" },
  { value: "3", label: "3 — Համանման ապրանքների գործարքի արժեքի որոշման մեթոդ" },
  { value: "4", label: "4 — Հանման մեթոդ" },
  { value: "5", label: "5 — Գումարման մեթոդ (ըստ հաշվարկային արժեքի)" },
  { value: "6", label: "6 — Պահուստային մեթոդ" },
];

const FILLED_SHIPMENT_GROUPS = [
  {
    id: "profile",
    title: "Դեկլարանտ",
    fields: [
      { key: "declarantName", label: "Ընկերության անվանում", span: 2 },
      { key: "declarantUnn", label: "ՀՎՀՀ", span: 1 },
      { key: "fillerName", label: "Լրացնող", span: 1 },
    ],
  },
  {
    id: "parties",
    title: "Կողմեր (հաշիվ-ապրանքագիր / ЦМР)",
    fields: [
      { key: "consignorName", label: "Ուղարկող (վաճառող)", span: 2 },
      { key: "senderCountry", label: "Ուղարկող երկիր", span: 2, type: "select", options: COUNTRY_CODE_OPTIONS },
      { key: "tradeCountry", label: "Առևտրի երկիր", span: 1 },
    ],
  },
  {
    id: "transport",
    title: "Փոխադրում (ЦМР)",
    fields: [
      { key: "borderOffice", label: "Սահմանային մաքսակետ", span: 2 },
      { key: "vehiclePlate", label: "Մեքենայի համարանիշ", span: 2 },
      { key: "trailerPlate", label: "Կցորդի համարանիշ", span: 2, type: "trailer" },
      { key: "transportQuantity", label: "Մեքենաների քանակ", span: 1 },
      { key: "containerIndicator", label: "Կոնտեյներ", span: 1, type: "select", options: [
        { value: "", label: "—" },
        { value: "Այո", label: "Այո" },
        { value: "Ոչ", label: "Ոչ" },
      ]},
      { key: "arrivalTransportMode", label: "Ժամանման միջոցներ", span: 1, type: "select", options: TRANSPORT_MODE_OPTIONS },
      { key: "borderTransportMode", label: "Սահմանահատման միջոցներ", span: 1, type: "select", options: TRANSPORT_MODE_OPTIONS },
    ],
  },
  {
    id: "commercial",
    title: "Պայմանագրային (հաշիվ-ապրանքագիր)",
    fields: [
      { key: "incoterms", label: "Incoterms (առաքման պայման)", span: 1 },
      { key: "incotermsPlace", label: "Incoterms վայր", span: 1 },
      { key: "contractCurrency", label: "Արժույթ", span: 1 },
      { key: "totalInvoiceAmount", label: "Ընդամենը գումար", span: 1 },
      { key: "totalGoodsNumber", label: "Ապրանքային տողեր", span: 1 },
      { key: "totalPackageNumber", label: "Ընդամենը փաթեթ", span: 1, placeholder: "CMR-ի և INVOICE-ի միջև առկա է անհամաձայնություն։ Լրացրեք ինքներդ" },
      // Per-declaration (identical for every goods line) → chosen once here, fanned out to all goods.
      { key: "customsMethod", label: "Մաքսային արժեքի որոշման մեթոդ", span: 2, type: "select", options: CUSTOMS_METHOD_OPTIONS },
    ],
  },
];

// The ReviewReport identifies what it flags by `concept` — a plain-language name, not an XML
// path. These two tables are the only place the panel maps a form field onto those names, and
// they must stay in lockstep with the concepts filing/writer.py and consistency/records.py emit.
const SHIPMENT_REVIEW_CONCEPTS = {
  declarantName: ["importer name", "importer"],
  declarantUnn: ["importer tax code"],
  fillerName: ["filler person"],
  consignorName: ["consignor name"],
  senderCountry: ["shipment origin country"],
  tradeCountry: ["trade country", "consignor country"],
  containerIndicator: ["container indicator"],
  incoterms: ["delivery terms code"],
  incotermsPlace: ["delivery terms"],
  contractCurrency: ["contract currency"],
  totalInvoiceAmount: ["total invoice amount"],
  totalPackageNumber: ["shipment package total"],
  customsMethod: ["line customs-value method"],
};

const GOODS_REVIEW_CONCEPTS = {
  description: ["line goods description", "goods description"],
  tnvedCode: ["line commodity code", "commodity code"],
  originCountry: ["line origin country"],
  quantity: ["line supplementary quantity"],
  quantityUnit: ["line supplementary quantity", "supplementary quantity unit"],
  packageQuantity: ["line package count"],
  packageTypeCode: ["line packaging classifier"],
};

// "omitted" is deliberately absent: it means nothing was written, which the empty-field red
// highlight already says. These three all mean a value IS present and is not to be trusted.
const FLAGGED_KINDS = new Set(["placeholder", "guess", "needs_review"]);

function matchingReviewItems(concepts, lineId, reviewItems) {
  if (!concepts || !reviewItems?.length) return [];
  return reviewItems.filter(
    (item) =>
      FLAGGED_KINDS.has(item.kind) &&
      concepts.includes(item.concept) &&
      (lineId === undefined || item.lineId === null || item.lineId === lineId),
  );
}

function flagText(items) {
  return items
    .map((item) => [item.detail, item.remedy].filter(Boolean).join(" — "))
    .filter(Boolean)
    .join("\n\n");
}

function isShipmentFieldFlagged(fieldKey, reviewItems) {
  return matchingReviewItems(SHIPMENT_REVIEW_CONCEPTS[fieldKey], undefined, reviewItems).length > 0;
}

function shipmentFieldFlagText(fieldKey, reviewItems) {
  return flagText(matchingReviewItems(SHIPMENT_REVIEW_CONCEPTS[fieldKey], undefined, reviewItems));
}

function isGoodsFieldFlagged(fieldKey, lineId, reviewItems) {
  return matchingReviewItems(GOODS_REVIEW_CONCEPTS[fieldKey], lineId, reviewItems).length > 0;
}

function goodsFieldFlagText(fieldKey, lineId, reviewItems) {
  return flagText(matchingReviewItems(GOODS_REVIEW_CONCEPTS[fieldKey], lineId, reviewItems));
}

const FILLED_GOODS_LABELS = {
  description: "Ապրանքի նկարագրություն",
  tnvedCode: "ԱՏԳ ԱԱ կոդ",
  quantity: "Քանակ",
  quantityUnit: "Չափման միավոր",
  netWeight: "Զուտ քաշ (կգ)",
  grossWeight: "Համախառն քաշ (կգ)",
  invoicedCost: "Ֆակտուրային արժեք",
  originCountry: "Ծագման երկիր",
  packageQuantity: "Փաթեթների քանակ",
  packageTypeCode: "Փաթեթավորման ծածկագիր",
  packingCode: "Փաթեթավորման կոդ",
};

function parseFilledDeclarationFromXml(xmlString) {
  const doc = parseXmlDoc(xmlString);
  const shipment = firstByLocalName(doc.documentElement, "ESADout_CUGoodsShipment");
  const consignment = firstByLocalName(shipment, "ESADout_CUConsigment");
  const consignor = firstByLocalName(shipment, "ESADout_CUConsignor");
  const declarant = firstByLocalName(shipment, "ESADout_CUDeclarant");
  const contractTerms = firstByLocalName(shipment, "ESADout_CUMainContractTerms");
  const deliveryTerms = firstByLocalName(contractTerms, "CUESADDeliveryTerms");
  const borderOffice = firstByLocalName(consignment, "BorderCustomsOffice");
  const transport = firstByLocalName(consignment, "ESADout_CUDepartureArrivalTransport");
  const borderTransport = firstByLocalName(consignment, "ESADout_CUBorderTransport");
  // One <TransportMeans> per plate on the CMR — the truck first, the trailer (if any) second.
  const plates = (transport ? [...transport.getElementsByTagNameNS("*", "TransportMeans")] : [])
    .map((m) => (m.getElementsByTagNameNS("*", "TransportIdentifier")[0]?.textContent ?? "").replace(/\s+/g, "").toUpperCase())
    .filter(Boolean);

  const tradeCode = textContentOf(contractTerms, "TradeCountryCode");

  return {
    declarantName: textContentOf(declarant, "OrganizationName"),
    declarantUnn: textContentOf(declarant, "UNN"),
    fillerName: "",
    consignorName: textContentOf(consignor, "OrganizationName"),
    senderCountry: textContentOf(consignment, "DispatchCountryCode"),
    tradeCountry: tradeCode,
    borderOffice: formatBorderOffice(borderOffice),
    vehiclePlate: plates[0] ?? "",
    trailerPlate: plates[1] ?? "",
    // Checkbox default: on when the model found a trailer plate; the user can toggle it either way.
    hasTrailer: plates.length > 1,
    arrivalTransportMode: textContentOf(transport, "TransportModeCode"),
    borderTransportMode: textContentOf(borderTransport, "TransportModeCode"),
    transportQuantity: textContentOf(transport, "TransportMeansQuantity"),
    containerIndicator: formatContainerIndicator(textContentOf(consignment, "ContainerIndicator")),
    incoterms: textContentOf(deliveryTerms, "DeliveryTermsStringCode"),
    incotermsPlace: textContentOf(deliveryTerms, "DeliveryPlace"),
    contractCurrency: textContentOf(contractTerms, "ContractCurrencyCode"),
    totalInvoiceAmount: textContentOf(contractTerms, "TotalInvoiceAmount"),
    currencyRate: textContentOf(contractTerms, "ContractCurrencyRate"),
    totalGoodsNumber: textContentOf(shipment, "TotalGoodsNumber"),
    totalPackageNumber: textContentOf(shipment, "TotalPackageNumber"),
    // Per-declaration value read off the first goods line (it is identical across all); defaults
    // to the agent's "1" (transaction value) so the dropdown is never blank.
    customsMethod: firstGoodsCustomsMethod(shipment) || "1",
  };
}

function enrichDeclarationFromProfile(meta, profile) {
  const filler = profile?.filler;
  const declarant = profile?.declarant;
  return {
    ...meta,
    declarantName: declarant?.organization_name?.trim() || meta.declarantName,
    declarantUnn: declarant?.unn?.trim() || meta.declarantUnn,
    fillerName:
      [filler?.surname, filler?.name].map((part) => part?.trim()).filter(Boolean).join(" ") ||
      meta.fillerName,
  };
}

function isPlaceholderValue(value) {
  const text = String(value ?? "").trim();
  return !text || text === PLACEHOLDER;
}

function inputValueFromDraft(value) {
  return isPlaceholderValue(value) ? "" : String(value ?? "");
}

function allShipmentFields() {
  return FILLED_SHIPMENT_GROUPS.flatMap((group) => group.fields);
}

function formatBorderOffice(node) {
  if (!node) return "";
  const code = textContentOf(node, "Code");
  const name = textContentOf(node, "OfficeName");
  if (code && name) return `${code} — ${name}`;
  return code || name;
}

function formatContainerIndicator(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "true") return "Այո";
  if (normalized === "false") return "Ոչ";
  return value ?? "";
}

// The customs-value method off the first goods line — it is consistent across the whole
// declaration, so one line's value represents all (the general card edits it once).
function firstGoodsCustomsMethod(shipment) {
  if (!shipment) return "";
  const goods = shipment.getElementsByTagNameNS("*", "ESADout_CUGoods")[0];
  return goods ? textContentOf(goods, "CustomsCostCorrectMethod") : "";
}

function parseFilledGoodsFromXml(xmlString) {
  const doc = parseXmlDoc(xmlString);

  const goodsNodes = [...doc.getElementsByTagNameNS("*", "ESADout_CUGoods")];
  return goodsNodes.map((node, index) => {
    const { quantity, unit } = parseGoodsLineQuantity(node);
    const packaging = firstByLocalName(node, "ESADGoodsPackaging");
    return {
      index,
      numeric: textContentOf(node, "GoodsNumeric") || String(index + 1),
      description: textContentOf(node, "GoodsDescription"),
      tnvedCode: textContentOf(node, "GoodsTNVEDCode"),
      originCountry: textContentOf(node, "OriginCountryCode"),
      quantity,
      quantityUnit: unit,
      netWeight: textContentOf(node, "NetWeightQuantity"),
      grossWeight: textContentOf(node, "GrossWeightQuantity"),
      invoicedCost: textContentOf(node, "InvoicedCost"),
      packageQuantity: textContentOf(packaging, "PakageQuantity"),
      packageTypeCode: textContentOf(packaging, "PakageTypeCode"),
      packingCode: textContentOf(packaging, "PackingCode"),
      // customsMethod is per-declaration, edited on the general card — not a per-goods field.
    };
  });
}
