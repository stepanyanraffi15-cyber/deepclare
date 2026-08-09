function parseXmlDoc(xmlString) {
  const doc = new DOMParser().parseFromString(xmlString, "application/xml");
  if (doc.querySelector("parsererror")) {
    throw new Error("Invalid declaration XML");
  }
  return doc;
}

function parseGoodsLineQuantity(goodsNode) {
  const supplementary = firstByLocalName(goodsNode, "SupplementaryGoodsQuantity");
  if (!supplementary) {
    return { quantity: "", unit: "" };
  }
  return {
    quantity: textContentOf(supplementary, "GoodsQuantity"),
    unit:
      textContentOf(supplementary, "MeasureUnitQualifierName") ||
      textContentOf(supplementary, "MeasureUnitQualifierCode"),
  };
}

function updateGoodsInXml(xmlString, goods) {
  const doc = parseXmlDoc(xmlString);

  const goodsNodes = [...doc.getElementsByTagNameNS("*", "ESADout_CUGoods")];
  for (const item of goods) {
    const node = goodsNodes[item.index];
    if (!node) continue;
    setTextContent(node, "GoodsDescription", item.description);
    setTextContent(node, "GoodsTNVEDCode", item.tnvedCode);
    // Weights and per-line origin are omitted by the agent when unknown — create-if-missing so a
    // value the user types into a blank field actually reaches the exported XML (issue #142).
    setInOrder(node, "catESAD_cu", "NetWeightQuantity", item.netWeight, GOODS_CHILD_ORDER);
    setInOrder(node, "catESAD_cu", "GrossWeightQuantity", item.grossWeight, GOODS_CHILD_ORDER);
    setTextContent(node, "InvoicedCost", item.invoicedCost);
    // Origin: the portal keys on the CODE (box 34), so write OriginCountryCode from the picked
    // country and fill OriginCountryName from it. Cleared → both removed (no half-written pair).
    const originCode = String(item.originCountry ?? "").trim();
    setInOrder(node, "catESAD_cu", "OriginCountryCode", originCode, GOODS_CHILD_ORDER);
    setInOrder(node, "catESAD_cu", "OriginCountryName",
      originCode ? (COUNTRY_NAME_BY_CODE[originCode] || "") : "", GOODS_CHILD_ORDER);
    // CustomsCostCorrectMethod is NOT per-line — it is fanned out to every good from the single
    // general-card value in updateDeclarationInXml (it must be identical across the declaration).
    const supplementary = firstByLocalName(node, "SupplementaryGoodsQuantity");
    if (supplementary) {
      setTextContent(supplementary, "GoodsQuantity", item.quantity);
      if (item.quantityUnit) {
        setTextContent(supplementary, "MeasureUnitQualifierName", item.quantityUnit);
      }
    }
    const packaging = firstByLocalName(node, "ESADGoodsPackaging");
    if (packaging) {
      // PakageQuantity is omitted when the agent has no count; create it before PakageTypeCode
      // (XSD order) so an edited package count is not silently dropped (issue #142 / #130).
      setInOrder(packaging, "catESAD_cu", "PakageQuantity", item.packageQuantity, PACKAGING_CHILD_ORDER);
      setTextContent(packaging, "PakageTypeCode", item.packageTypeCode);
      const packingCode = String(item.packingCode ?? "").trim();
      let packingInfo = firstByLocalName(packaging, "PackingInformation");
      if (packingCode) {
        // Create the block when the line had none (agent omits it without a mapped method). XSD
        // sequences PackingInformation after PakageTypeCode, so append (packaging holds only
        // PakageQuantity/PakageTypeCode); children order is PackingCode then PakingQuantity.
        if (!packingInfo) {
          packingInfo = appendNsChild(packaging, "catESAD_cu", "PackingInformation", "");
        }
        setOrCreateText(packingInfo, "catESAD_cu", "PackingCode", packingCode, "PakingQuantity");
        // The renderer files PakingQuantity equal to the package count; keep them in sync
        // so an edited count doesn't leave the two package totals contradicting each other.
        setOrCreateText(packingInfo, "catESAD_cu", "PakingQuantity", item.packageQuantity, null);
      } else if (packingInfo) {
        // No code chosen — drop the block rather than leave an empty (schema-invalid) PackingCode.
        packingInfo.parentNode.removeChild(packingInfo);
      }
    }
  }

  return new XMLSerializer().serializeToString(doc);
}

function updateDeclarationInXml(xmlString, declaration) {
  const doc = parseXmlDoc(xmlString);
  const shipment = firstByLocalName(doc.documentElement, "ESADout_CUGoodsShipment");
  const consignment = firstByLocalName(shipment, "ESADout_CUConsigment");
  const consignor = firstByLocalName(shipment, "ESADout_CUConsignor");
  const consignee = firstByLocalName(shipment, "ESADout_CUConsignee");
  const declarant = firstByLocalName(shipment, "ESADout_CUDeclarant");
  const finPerson = firstByLocalName(shipment, "ESADout_CUFinancialAdjustingResponsiblePerson");
  const contractTerms = firstByLocalName(shipment, "ESADout_CUMainContractTerms");
  const deliveryTerms = firstByLocalName(contractTerms, "CUESADDeliveryTerms");
  const transport = firstByLocalName(consignment, "ESADout_CUDepartureArrivalTransport");

  for (const party of [consignee, declarant, finPerson]) {
    if (!party) continue;
    setTextContent(party, "OrganizationName", declaration.declarantName);
    setTextContent(party, "UNN", declaration.declarantUnn);
  }

  setTextContent(consignor, "OrganizationName", declaration.consignorName);
  // Fields the agent may OMIT when unknown (no CMR, undetermined route, …) are created if the
  // user pulls a value into them — inserted at the correct XSD position before a stable anchor
  // that always exists, so the download stays schema-valid. Never created empty (would be an
  // invalid typed leaf); a blank value just leaves the element absent.
  // Departure country: the portal keys on the CODE, so write DispatchCountryCode from the picked
  // country and fill DispatchCountryName from it. Both anchored before DestinationCountryCode, code
  // first, so the XSD sequence (DispatchCountryCode, DispatchCountryName, Destination…) holds.
  const departureCode = String(declaration.senderCountry ?? "").trim();
  setOrCreateText(consignment, "catESAD_cu", "DispatchCountryCode", departureCode, "DestinationCountryCode");
  setOrCreateText(
    consignment,
    "catESAD_cu",
    "DispatchCountryName",
    departureCode ? COUNTRY_NAME_BY_CODE[departureCode] || "" : "",
    "DestinationCountryCode",
  );
  // Shipment-level (general) origin is intentionally NOT filled (ADR-0024): origin is declared
  // per goods line only (updateGoodsInXml), so we do not touch the shipment OriginCountryName.
  setOrCreateText(
    contractTerms,
    "catESAD_cu",
    "TradeCountryCode",
    declaration.tradeCountry,
    "CUESADDeliveryTerms",
  );
  applyBorderOffice(consignment, declaration.borderOffice);

  const borderTransport = firstByLocalName(consignment, "ESADout_CUBorderTransport");
  // Vehicle + trailer plates are two separate fields (ADR-0024): the truck is the first
  // <TransportMeans>, the trailer the second — written only when the user kept its checkbox on.
  // Applied to both the departure/arrival and the border transport blocks.
  const vehiclePlate = (declaration.vehiclePlate ?? "").trim();
  const trailerPlate = declaration.hasTrailer ? (declaration.trailerPlate ?? "").trim() : "";
  setTransportPlates(transport, vehiclePlate, trailerPlate);
  setTransportPlates(borderTransport, vehiclePlate, trailerPlate);
  setOrCreateText(transport, "ESADout_CU", "TransportMeansQuantity", declaration.transportQuantity, "TransportMeans");
  setOrCreateText(borderTransport, "ESADout_CU", "TransportMeansQuantity", declaration.transportQuantity, "TransportMeans");
  // Transport mode codes (30/31): arrival/departure and border transport (agent defaults 31).
  setTextContent(transport, "TransportModeCode", declaration.arrivalTransportMode);
  setTextContent(borderTransport, "TransportModeCode", declaration.borderTransportMode);
  setTextContent(
    consignment,
    "ContainerIndicator",
    containerIndicatorToXml(declaration.containerIndicator),
  );
  setTextContent(deliveryTerms, "DeliveryTermsStringCode", declaration.incoterms);
  setTextContent(deliveryTerms, "DeliveryPlace", declaration.incotermsPlace);
  setTextContent(contractTerms, "ContractCurrencyCode", declaration.contractCurrency);
  setTextContent(contractTerms, "TotalInvoiceAmount", declaration.totalInvoiceAmount);
  setTextContent(shipment, "TotalGoodsNumber", declaration.totalGoodsNumber);
  setTextContent(shipment, "TotalPackageNumber", declaration.totalPackageNumber);

  // Customs-value determination method (box 43): one method per declaration, edited once on the
  // general card and applied to EVERY goods line here (the XML still carries it per <Goods>, so
  // the under-the-hood shape is unchanged). Empty is not written, so goods keep their value.
  const customsMethod = String(declaration.customsMethod ?? "").trim();
  if (customsMethod) {
    for (const good of doc.getElementsByTagNameNS("*", "ESADout_CUGoods")) {
      setTextContent(good, "CustomsCostCorrectMethod", customsMethod);
    }
  }

  return new XMLSerializer().serializeToString(doc);
}

// Write the truck plate to the first <TransportMeans> and the trailer plate to the second,
// creating/removing the second so the checkbox state (ADR-0024) is honoured. A block that had
// no <TransportMeans> (a plate-less degraded run) gets one created so a user-entered plate the
// model missed still writes.
function setTransportPlates(block, vehiclePlate, trailerPlate) {
  if (!block) return;
  let means = [...block.getElementsByTagNameNS("*", "TransportMeans")];

  if (means.length === 0) {
    if (!vehiclePlate && !trailerPlate) return; // nothing to write, don't create an empty means
    createTransportMeans(block, "");
    means = [...block.getElementsByTagNameNS("*", "TransportMeans")];
  }
  setTextContent(means[0], "TransportIdentifier", vehiclePlate);

  if (trailerPlate) {
    if (!means[1]) {
      // Clone the truck's <TransportMeans> to keep the same structure/namespaces, then relabel.
      const clone = means[0].cloneNode(true);
      means[0].parentNode.insertBefore(clone, means[0].nextSibling);
      means = [...block.getElementsByTagNameNS("*", "TransportMeans")];
    }
    setTextContent(means[1], "TransportIdentifier", trailerPlate);
  } else {
    // No trailer kept → drop every <TransportMeans> after the first.
    for (let i = means.length - 1; i >= 1; i--) {
      means[i].parentNode.removeChild(means[i]);
    }
  }
}

function createTransportMeans(block, identifier) {
  const doc = block.ownerDocument;
  const means = doc.createElementNS(nsUriFor(doc, "ESADout_CU"), "ESADout_CU:TransportMeans");
  appendNsChild(means, "cat_ru", "TransportIdentifier", identifier);
  block.appendChild(means);
  return means;
}

function containerIndicatorToXml(value) {
  const text = String(value ?? "").trim();
  if (text === "Այո") return "true";
  if (text === "Ոչ") return "false";
  return text;
}

function applyBorderOffice(consignment, value) {
  if (!consignment) return;
  const text = String(value ?? "").trim();
  const split = text.split(" — ");
  let node = firstByLocalName(consignment, "BorderCustomsOffice");
  if (!node) {
    // Create the block only with a "Code — OfficeName" value: the Code is a required,
    // pattern-restricted leaf, so a block without it would be schema-invalid.
    if (split.length < 2) return;
    const doc = consignment.ownerDocument;
    node = doc.createElementNS(nsUriFor(doc, "catESAD_cu"), "catESAD_cu:BorderCustomsOffice");
    consignment.insertBefore(
      node,
      firstByLocalName(consignment, "ESADout_CUDepartureArrivalTransport"),
    );
    appendNsChild(node, "cat_ru", "Code", "");
    appendNsChild(node, "cat_ru", "OfficeName", "");
    appendNsChild(node, "cat_ru", "CustomsCountryCode", "AM");
  }
  if (split.length >= 2) {
    setTextContent(node, "Code", split[0].trim());
    setTextContent(node, "OfficeName", split.slice(1).join(" — ").trim());
    return;
  }
  setTextContent(node, "OfficeName", text);
}

// Resolve a declared namespace prefix (catESAD_cu / ESADout_CU / cat_ru) to its URI.
function nsUriFor(doc, prefix) {
  return (
    doc.documentElement.getAttribute("xmlns:" + prefix) ||
    doc.documentElement.lookupNamespaceURI(prefix) ||
    ""
  );
}

function appendNsChild(parent, prefix, localName, value) {
  const doc = parent.ownerDocument;
  const el = doc.createElementNS(nsUriFor(doc, prefix), prefix + ":" + localName);
  el.textContent = value ?? "";
  parent.appendChild(el);
  return el;
}

// Set a value, creating the element (in `prefix` namespace, before `anchorLocalName`) when it is
// missing — so a user-pulled value writes back even into a field the agent omitted. Never creates
// an empty element (an empty typed leaf is schema-invalid); a blank value on a missing node is a
// no-op.
function setOrCreateText(parent, prefix, localName, value, anchorLocalName) {
  if (!parent) return;
  let node = firstByLocalName(parent, localName);
  const text = String(value ?? "").trim();
  if (!text) {
    // Cleared → remove rather than leave an empty (schema-invalid) leaf.
    if (node && node.parentNode) node.parentNode.removeChild(node);
    return;
  }
  if (!node) {
    const doc = parent.ownerDocument;
    node = doc.createElementNS(nsUriFor(doc, prefix), prefix + ":" + localName);
    const anchor = anchorLocalName ? firstByLocalName(parent, anchorLocalName) : null;
    parent.insertBefore(node, anchor && anchor.parentNode === parent ? anchor : null);
  }
  node.textContent = text;
}

// XSD child order (local names) for the goods elements the extension may need to *insert*. An edit
// to a field the agent omitted must be created in its sequence slot, or the portal rejects the whole
// file's format (see fbef8e8 / issue #142). Order taken from the real portal-accepted declarations.
const GOODS_CHILD_ORDER = [
  "GoodsNumeric", "GoodsDescription", "GrossWeightQuantity", "NetWeightQuantity", "InvoicedCost",
  "GoodsTNVEDCode", "AdditionalSign", "OriginCountryCode", "OriginCountryName",
  "CustomsCostCorrectMethod", "Preferencii", "ESADout_CUPresentedDocument",
  "ESADout_CUCustomsPaymentCalculation", "SupplementaryGoodsQuantity", "ESADGoodsPackaging",
  "ESADCustomsProcedure",
];
const PACKAGING_CHILD_ORDER = [
  "PakageQuantity", "PakageTypeCode", "PakagePartQuantity", "RBCargoKind", "PackageCode",
  "PackingInformation", "PalleteInformation",
];

// Set a leaf's text, creating the element in its XSD-sequence slot (per `order`) when it is absent —
// so an edit to a field the agent omitted survives export instead of being a silent no-op
// (setTextContent only updates an existing node). Never creates an empty leaf (schema-invalid).
function setInOrder(parent, prefix, localName, value, order) {
  if (!parent) return;
  const existing = firstByLocalName(parent, localName);
  const text = String(value ?? "").trim();
  if (!text) {
    // Cleared → remove the element rather than leave an empty (schema-invalid) leaf.
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
    return;
  }
  if (existing) {
    existing.textContent = text;
    return;
  }
  const doc = parent.ownerDocument;
  const node = doc.createElementNS(nsUriFor(doc, prefix), `${prefix}:${localName}`);
  node.textContent = text;
  const pos = order.indexOf(localName);
  let anchor = null;
  for (const child of parent.children) {
    if (order.indexOf(child.localName) > pos) {
      anchor = child;
      break;
    }
  }
  parent.insertBefore(node, anchor);
}

function addGoodsToXml(xmlString) {
  const doc = parseXmlDoc(xmlString);
  const goodsNodes = [...doc.getElementsByTagNameNS("*", "ESADout_CUGoods")];
  if (goodsNodes.length === 0) return xmlString;

  const last = goodsNodes[goodsNodes.length - 1];
  const clone = last.cloneNode(true);

  for (const text of [...clone.getElementsByTagName("*")]) {
    if (text.childElementCount === 0) text.textContent = "";
  }
  setTextContent(clone, "GoodsNumeric", String(goodsNodes.length + 1));

  last.parentNode.insertBefore(clone, last.nextSibling);
  return new XMLSerializer().serializeToString(doc);
}

function removeGoodsFromXml(xmlString, index) {
  const doc = parseXmlDoc(xmlString);
  const goodsNodes = [...doc.getElementsByTagNameNS("*", "ESADout_CUGoods")];
  const target = goodsNodes[index];
  if (!target) return xmlString;

  target.parentNode.removeChild(target);

  const remaining = [...doc.getElementsByTagNameNS("*", "ESADout_CUGoods")];
  remaining.forEach((node, i) => {
    setTextContent(node, "GoodsNumeric", String(i + 1));
  });

  return new XMLSerializer().serializeToString(doc);
}

function firstByLocalName(parent, localName) {
  if (!parent) return null;
  return parent.getElementsByTagNameNS("*", localName)[0] ?? null;
}

function textContentOf(parent, localName) {
  const node = firstByLocalName(parent, localName);
  return node?.textContent?.trim() ?? "";
}

function setTextContent(parent, localName, value) {
  if (!parent) return;
  const node = firstByLocalName(parent, localName);
  if (node) node.textContent = value ?? "";
}
