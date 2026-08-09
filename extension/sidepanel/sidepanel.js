const MIN_FILES = 1;
const THEME_KEY = "theme";
const WORKFLOW_KEY = "workflow";

const STATE = {
  IDLE: "idle",
  LOADING: "loading",
  PROCESSING: "processing",
  EDIT: "edit",
  ERROR: "error",
};

// The server reports 16 granular stages (see deepclare.run.pipeline); the panel groups
// them into 5 phases for display. `stages` lists every raw name that falls in the phase,
// in pipeline order — updateProgress/stageLabel match a reported stage against these.
const STEP_GROUPS = [
  {
    label: "Ընդունել և կարդալ փաստաթղթերը",
    stages: [
      "intake",
      "rasterize",
      "classify pages",
      "group pages",
      "read documents",
      "goods gate",
      "enrich evidence",
    ],
  },
  {
    label: "Գրել նկարագրությունները",
    stages: ["build line contexts", "write descriptions"],
  },
  {
    label: "Որոշել ԱՏԳ կոդերը",
    stages: ["classify lines", "completeness guard"],
  },
  {
    label: "Հավաքել հայտարարագիրը",
    stages: ["assemble lines", "reconcile lines", "assemble declaration", "write filing"],
  },
  {
    label: "Կազմել ստուգման հաշվետվությունը",
    stages: ["build review report"],
  },
];

const headerSubtitle = document.getElementById("header-subtitle");
const newRunBtn = document.getElementById("new-run-btn");
const profileBtn = document.getElementById("profile-btn");
const settingsBtn = document.getElementById("settings-btn");
const connectionBanner = document.getElementById("connection-banner");
const connectionBannerText = document.getElementById("connection-banner-text");
const connectionSettingsBtn = document.getElementById("connection-settings-btn");

const profilePanel = document.getElementById("profile-panel");
const profileBackBtn = document.getElementById("profile-back");
const profileOrganizationInput = document.getElementById("profile-organization");
const profileTaxCodeInput = document.getElementById("profile-tax-code");
const profileStreetHouseInput = document.getElementById("profile-street-house");
const profileFillerSurnameInput = document.getElementById("profile-filler-surname");
const profileFillerGivenNameInput = document.getElementById("profile-filler-given-name");
const profileError = document.getElementById("profile-error");
const profileSaveBtn = document.getElementById("profile-save");

const filesInput = document.getElementById("files");
const fileZone = document.getElementById("file-zone");
const fileZoneLabelEl = document.querySelector(".file-zone-label");
const fileHintEl = document.getElementById("file-hint");
const fileCountEl = document.getElementById("file-count");
const fileListEl = document.getElementById("file-list");

const actionBtn = document.getElementById("action");
const progressSection = document.getElementById("progress");

const summarySection = document.getElementById("summary-section");
const summaryGrid = document.getElementById("summary-grid");
const summaryNotes = document.getElementById("summary-notes");

const declarationInfoSection = document.getElementById("declaration-info-section");
const declarationInfoForm = document.getElementById("declaration-info-form");

const goodsSection = document.getElementById("goods-section");
const goodsList = document.getElementById("goods-list");
const goodsSearchInput = document.getElementById("goods-search");
const goodsSearchCount = document.getElementById("goods-search-count");
const addGoodsBtn = document.getElementById("add-goods");
const saveGoodsBtn = document.getElementById("save-goods");
const downloadExcelBtn = document.getElementById("download-excel");
const downloadXmlBtn = document.getElementById("download-xml");
const saveStatus = document.getElementById("save-status");

const extensionVersionEl = document.getElementById("extension-version");

let state = STATE.IDLE;
let connection = { serverUrl: "", hasToken: false, reachable: false, reason: null };
let profile = emptyProfile();
let selectedFiles = [];
let pendingDocuments = [];
let result = null;
let declarationDraft = null;
let goodsDraft = [];
let reviewItems = [];
let activeJobId = null;
let activeFilename = null;
let pollTimer = null;
let lastKnownStepIndex = -1;
let goodsSearchHits = [];
let goodsSearchPos = -1;

applyTheme(osTheme());
void initTheme();
for (const btn of document.querySelectorAll(".theme-toggle")) {
  btn.addEventListener("click", () => void toggleTheme());
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", async (event) => {
  const { [THEME_KEY]: theme } = await chrome.storage.local.get(THEME_KEY);
  if (!theme) applyTheme(event.matches ? "dark" : "light");
});

buildProgress();
void init();

function emptyProfile() {
  return {
    organizationName: "",
    taxCode: "",
    streetHouse: "",
    fillerSurname: "",
    fillerGivenName: "",
  };
}

function isProfileComplete(candidate) {
  return Boolean(candidate?.organizationName?.trim() && candidate?.taxCode?.trim());
}

function osTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  for (const btn of document.querySelectorAll(".theme-toggle")) {
    btn.textContent = theme === "dark" ? "☀️" : "🌙";
  }
}

async function initTheme() {
  const { [THEME_KEY]: theme } = await chrome.storage.local.get(THEME_KEY);
  if (theme) applyTheme(theme);
}

async function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  await chrome.storage.local.set({ [THEME_KEY]: next });
  applyTheme(next);
}

async function init() {
  extensionVersionEl.textContent = `v${chrome.runtime.getManifest().version}`;
  await loadProfile();
  await refreshConnection();
  await restoreWorkflow();
  updateUi();
}

async function send(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) throw new Error(response?.error || "Անհայտ սխալ");
  return response;
}

async function refreshConnection() {
  try {
    const response = await send({ type: "get-connection" });
    connection = response.connection;
  } catch (error) {
    connection = { serverUrl: "", hasToken: false, reachable: false, reason: String(error) };
  }
  renderConnection();
}

function renderConnection() {
  headerSubtitle.textContent = connection.serverUrl || "Կարգավորված չէ";
  if (!connection.hasToken) {
    connectionBannerText.textContent = "Թոքենը լրացված չէ — բացեք կարգավորումները";
    connectionBanner.hidden = false;
    return;
  }
  if (!connection.reachable) {
    connectionBannerText.textContent = connection.reason
      ? `Ծառայությունն անհասանելի է՝ ${connection.reason}`
      : "Ծառայությունն անհասանելի է";
    connectionBanner.hidden = false;
    return;
  }
  connectionBanner.hidden = true;
}

settingsBtn.addEventListener("click", () => chrome.runtime.openOptionsPage());
connectionSettingsBtn.addEventListener("click", () => chrome.runtime.openOptionsPage());
profileBtn.addEventListener("click", () => openProfilePanel());
profileBackBtn.addEventListener("click", () => {
  profilePanel.hidden = true;
});
profileSaveBtn.addEventListener("click", () => void saveProfilePanel());
newRunBtn.addEventListener("click", () => void startNewRun());

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") profilePanel.hidden = true;
});

chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area !== "local") return;
  if (!changes.serverUrl && !changes.serviceToken) return;
  await refreshConnection();
  updateUi();
});

async function loadProfile() {
  try {
    const response = await send({ type: "get-profile" });
    profile = { ...emptyProfile(), ...response.profile };
  } catch {
    profile = emptyProfile();
  }
}

function openProfilePanel() {
  profileOrganizationInput.value = profile.organizationName;
  profileTaxCodeInput.value = profile.taxCode;
  profileStreetHouseInput.value = profile.streetHouse;
  profileFillerSurnameInput.value = profile.fillerSurname;
  profileFillerGivenNameInput.value = profile.fillerGivenName;
  profileError.hidden = true;
  profilePanel.hidden = false;
}

function readProfilePanel() {
  return {
    organizationName: profileOrganizationInput.value.trim(),
    taxCode: profileTaxCodeInput.value.trim(),
    streetHouse: profileStreetHouseInput.value.trim(),
    fillerSurname: profileFillerSurnameInput.value.trim(),
    fillerGivenName: profileFillerGivenNameInput.value.trim(),
  };
}

async function saveProfilePanel() {
  const candidate = readProfilePanel();
  if (!isProfileComplete(candidate)) {
    profileError.textContent = "Լրացրեք ընկերության անվանումն ու ՀՎՀՀ-ն";
    profileError.hidden = false;
    return;
  }
  profileSaveBtn.disabled = true;
  try {
    const response = await send({ type: "save-profile", profile: candidate });
    profile = { ...emptyProfile(), ...response.profile };
    profilePanel.hidden = true;
    if (declarationDraft) {
      declarationDraft = enrichDeclarationFromProfile(declarationDraft, toFilledProfile(profile));
      renderDeclarationInfo();
    }
    updateUi();
  } catch (error) {
    profileError.textContent = String(error.message ?? error);
    profileError.hidden = false;
  } finally {
    profileSaveBtn.disabled = false;
  }
}

function toFilledProfile(source) {
  return {
    declarant: { organization_name: source.organizationName, unn: source.taxCode },
    filler: { surname: source.fillerSurname, name: source.fillerGivenName },
  };
}

function buildProgress() {
  const list = document.createElement("ol");
  list.className = "progress-steps";
  for (const group of STEP_GROUPS) {
    const item = document.createElement("li");
    item.className = "progress-step is-pending";
    const icon = document.createElement("span");
    icon.className = "step-icon";
    const label = document.createElement("span");
    label.className = "step-label";
    label.textContent = group.label;
    item.append(icon, label);
    list.append(item);
  }
  const bar = document.createElement("div");
  bar.className = "progress-bar";
  const fill = document.createElement("div");
  fill.className = "progress-bar-fill";
  bar.append(fill);
  progressSection.replaceChildren(list, bar);
}

function groupIndexForStage(stage) {
  return STEP_GROUPS.findIndex((group) => group.stages.includes(stage));
}

function updateProgress(status, stage) {
  if (status === "queued") {
    lastKnownStepIndex = -1;
  } else {
    const found = groupIndexForStage(stage);
    if (found >= 0) lastKnownStepIndex = found;
  }
  const activeIndex = lastKnownStepIndex;
  progressSection.querySelectorAll(".progress-step").forEach((item, i) => {
    const done = activeIndex >= 0 && i < activeIndex;
    const active = i === activeIndex;
    item.classList.toggle("is-done", done);
    item.classList.toggle("is-active", active);
    item.classList.toggle("is-pending", !done && !active);
    item.querySelector(".step-icon").textContent = done ? "✓" : "";
  });
  const fill = progressSection.querySelector(".progress-bar-fill");
  fill.style.width =
    activeIndex < 0 ? "4%" : `${((activeIndex + 1) / STEP_GROUPS.length) * 100}%`;
}

function stageLabel(status, stage) {
  if (status === "queued") return "Հերթում է…";
  const group = STEP_GROUPS[groupIndexForStage(stage)];
  return group ? `${group.label}…` : "Մշակվում է…";
}

filesInput.addEventListener("change", () => {
  const picked = Array.from(filesInput.files ?? []);
  filesInput.value = "";
  void addFiles(picked);
});

fileZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  fileZone.classList.add("dragover");
});

fileZone.addEventListener("dragleave", () => fileZone.classList.remove("dragover"));

fileZone.addEventListener("drop", (event) => {
  event.preventDefault();
  fileZone.classList.remove("dragover");
  void addFiles(Array.from(event.dataTransfer?.files ?? []));
});

async function addFiles(incoming) {
  if (incoming.length === 0) return;
  if (state !== STATE.IDLE) teardownRun();
  selectedFiles = [...selectedFiles, ...incoming];
  await syncDocuments();
}

function removeFile(index) {
  selectedFiles = selectedFiles.filter((_, i) => i !== index);
  if (state !== STATE.IDLE) teardownRun();
  void syncDocuments();
}

async function syncDocuments() {
  pendingDocuments = await Promise.all(selectedFiles.map(encodeDocument));
  if (pendingDocuments.length > 0) {
    await saveWorkflow({ phase: "ready", documents: pendingDocuments });
  } else {
    await clearWorkflow();
  }
  updateUi();
}

async function encodeDocument(file) {
  return {
    fileName: file.name,
    contentBase64: await fileToBase64(file),
    mediaType: file.type || null,
  };
}

function documentToFile(doc) {
  return new File([base64ToBytes(doc.contentBase64)], doc.fileName, {
    type: doc.mediaType || "",
  });
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function previewFile(file) {
  window.open(URL.createObjectURL(file), "_blank");
}

function renderFileList() {
  if (selectedFiles.length === 0) {
    fileListEl.hidden = true;
    fileListEl.replaceChildren();
    return;
  }
  fileListEl.replaceChildren();
  selectedFiles.forEach((file, i) => {
    const chip = document.createElement("div");
    chip.className = "file-chip";

    const nameBtn = document.createElement("button");
    nameBtn.type = "button";
    nameBtn.className = "file-chip-name";
    nameBtn.title = file.name;
    nameBtn.textContent = file.name;
    nameBtn.addEventListener("click", () => previewFile(file));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "file-chip-remove";
    removeBtn.textContent = "×";
    removeBtn.title = "Հեռացնել";
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      removeFile(i);
    });

    chip.append(nameBtn, removeBtn);
    fileListEl.append(chip);
  });
  fileListEl.hidden = false;
}

function saveWorkflow(workflow) {
  return chrome.storage.local.set({ [WORKFLOW_KEY]: workflow });
}

function clearWorkflow() {
  return chrome.storage.local.remove(WORKFLOW_KEY);
}

async function restoreWorkflow() {
  const stored = await chrome.storage.local.get(WORKFLOW_KEY);
  const workflow = stored[WORKFLOW_KEY];
  if (!workflow) return;
  if (workflow.phase === "ready" && workflow.documents?.length) {
    pendingDocuments = workflow.documents;
    selectedFiles = workflow.documents.map(documentToFile);
    setState(STATE.IDLE);
    return;
  }
  if (workflow.phase === "processing" && workflow.jobId) {
    startPolling(workflow.jobId, workflow.filename);
    return;
  }
  if (workflow.phase === "edit" && workflow.xml) {
    applyResult({
      declarationXml: workflow.xml,
      filename: workflow.filename,
      summary: workflow.summary ?? null,
      reviewReport: workflow.reviewReport ?? null,
    });
  }
}

actionBtn.addEventListener("click", () => {
  if (state === STATE.ERROR) {
    teardownRun();
    void runPipeline();
    return;
  }
  if (state !== STATE.IDLE) return;
  void runPipeline();
});

function downloadNameFrom(documents) {
  const first = documents[0];
  const base = (first?.fileName ?? "declaration").replace(/\.[^.]+$/, "");
  return `${base}.declaration.xml`;
}

async function runPipeline() {
  setState(STATE.LOADING);
  hideResult();
  try {
    const filename = downloadNameFrom(pendingDocuments);
    const response = await send({
      type: "submit-run",
      files: pendingDocuments.map((doc) => ({
        fileName: doc.fileName,
        contentBase64: doc.contentBase64,
      })),
      profile,
    });
    await saveWorkflow({ phase: "processing", jobId: response.jobId, filename });
    startPolling(response.jobId, filename);
  } catch (error) {
    setState(STATE.ERROR, String(error.message ?? error));
  }
}

function startPolling(jobId, filename) {
  activeJobId = jobId;
  activeFilename = filename;
  stopPolling();
  setState(STATE.PROCESSING, "Հերթում է…");
  updateProgress("queued", null);
  void pollOnce();
  pollTimer = setInterval(() => void pollOnce(), 2000);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollOnce() {
  const jobId = activeJobId;
  if (!jobId) return;

  let response;
  try {
    response = await send({ type: "poll-run", jobId });
  } catch (error) {
    if (activeJobId !== jobId) return;
    stopPolling();
    void clearWorkflow();
    setState(STATE.ERROR, String(error.message ?? error));
    return;
  }
  if (activeJobId !== jobId) return;

  if (response.status === "succeeded") {
    stopPolling();
    applyResult({
      declarationXml: response.declarationXml,
      filename: activeFilename,
      summary: response.summary,
      reviewReport: response.reviewReport,
    });
    return;
  }
  if (response.status === "failed") {
    stopPolling();
    void clearWorkflow();
    setState(STATE.ERROR, response.error || "Մշակումը ձախողվեց");
    return;
  }
  setState(STATE.PROCESSING, stageLabel(response.status, response.stage));
  updateProgress(response.status, response.stage);
}

function applyResult({ declarationXml, filename, summary, reviewReport }) {
  result = {
    xml: declarationXml,
    filename: filename || "declaration.xml",
    summary: summary ?? null,
    reviewReport: reviewReport ?? null,
  };
  reviewItems = flattenReviewItems(result.reviewReport);
  declarationDraft = enrichDeclarationFromProfile(
    parseFilledDeclarationFromXml(result.xml),
    toFilledProfile(profile),
  );
  goodsDraft = parseFilledGoodsFromXml(result.xml);
  void saveWorkflow({
    phase: "edit",
    xml: result.xml,
    filename: result.filename,
    summary: result.summary,
    reviewReport: result.reviewReport,
  });
  renderSummary();
  renderDeclarationInfo();
  renderGoodsForm();
  setState(STATE.EDIT);
}

function flattenReviewItems(report) {
  const items = [];
  for (const group of report?.groups ?? []) {
    for (const entry of group.entries ?? []) {
      const item = entry.item ?? {};
      items.push({
        kind: item.kind ?? null,
        concept: item.concept ?? null,
        detail: item.detail ?? null,
        remedy: item.remedy ?? null,
        lineId: item.line_id ?? group.line_id ?? null,
        shown: entry.value?.shown ?? null,
      });
    }
  }
  return items;
}

function renderSummary() {
  const summary = result?.summary;
  if (!summary) {
    summarySection.hidden = true;
    return;
  }
  const yesNo = (value) => (value ? "Այո" : "Ոչ");
  const rows = [
    ["Ապրանքային տողեր", String(summary.goods_line_count ?? 0)],
    ["Նշանակված ԱՏԳ կոդեր", String(summary.codes_assigned ?? 0)],
    ["Ձեռնպահ մնացած կոդեր", String(summary.codes_abstained ?? 0)],
    ["Համապատասխանում է սխեմային", yesNo(summary.conforms)],
    ["Ներկայացնելի է", yesNo(summary.filable)],
  ];
  summaryGrid.replaceChildren();
  for (const [label, value] of rows) {
    const cell = document.createElement("div");
    cell.className = "summary-cell";
    const caption = document.createElement("span");
    caption.className = "summary-label";
    caption.textContent = label;
    const shown = document.createElement("span");
    shown.className = "summary-value";
    shown.textContent = value;
    cell.append(caption, shown);
    summaryGrid.append(cell);
  }
  summaryGrid.classList.toggle("is-not-filable", summary.filable === false);

  const notes = summary.notes ?? [];
  summaryNotes.replaceChildren();
  for (const note of notes) {
    const item = document.createElement("li");
    item.textContent = note;
    summaryNotes.append(item);
  }
  summaryNotes.hidden = notes.length === 0;
  summarySection.hidden = false;
}

function createShipmentFieldControl(field, value) {
  if (field.type === "select") {
    const control = document.createElement("select");
    for (const option of field.options) {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      control.append(node);
    }
    control.value = inputValueFromDraft(value);
    return control;
  }
  const control = document.createElement("input");
  control.type = "text";
  control.value = inputValueFromDraft(value);
  if (field.placeholder) control.placeholder = field.placeholder;
  return control;
}

function renderDeclarationInfo() {
  if (!declarationDraft) return;
  declarationInfoForm.replaceChildren();

  for (const group of FILLED_SHIPMENT_GROUPS) {
    const section = document.createElement("section");
    section.className = "declaration-info-group";

    const heading = document.createElement("h3");
    heading.textContent = group.title;
    section.append(heading);

    const grid = document.createElement("div");
    grid.className = "declaration-info-form";

    for (const field of group.fields) {
      if (field.type === "trailer") {
        grid.append(renderTrailerField(field));
        continue;
      }
      const label = document.createElement("label");
      label.className = field.span === 2 ? "span-2" : "";

      const caption = document.createElement("span");
      caption.textContent = field.label;
      label.append(caption);

      const control = createShipmentFieldControl(field, declarationDraft[field.key] ?? "");
      control.dataset.field = field.key;
      // senderCountry (dispatch country) is exempt from the empty-field red highlight.
      if (field.key !== "senderCountry") bindMissingHighlight(control);
      if (isShipmentFieldFlagged(field.key, reviewItems)) {
        control.classList.add("is-flagged");
        control.title = shipmentFieldFlagText(field.key, reviewItems);
      }
      label.append(control);
      grid.append(label);
    }

    section.append(grid);
    declarationInfoForm.append(section);
  }
  declarationInfoSection.hidden = false;
}

function renderTrailerField(field) {
  const wrap = document.createElement("div");
  wrap.className = field.span === 2 ? "span-2 trailer-field" : "trailer-field";

  const toggle = document.createElement("label");
  toggle.className = "trailer-toggle";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.dataset.field = "hasTrailer";
  checkbox.checked = Boolean(declarationDraft.hasTrailer);
  const toggleText = document.createElement("span");
  toggleText.textContent = field.label;
  toggle.append(checkbox, toggleText);

  const input = document.createElement("input");
  input.type = "text";
  input.dataset.field = "trailerPlate";
  input.placeholder = field.label;
  input.value = inputValueFromDraft(declarationDraft.trailerPlate ?? "");
  input.hidden = !checkbox.checked;
  bindMissingHighlight(input);

  checkbox.addEventListener("change", () => {
    input.hidden = !checkbox.checked;
    if (!checkbox.checked) input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  wrap.append(toggle, input);
  return wrap;
}

function collectDeclarationFromForm() {
  if (!declarationDraft) return;
  for (const field of allShipmentFields()) {
    const control = declarationInfoForm.querySelector(`[data-field="${field.key}"]`);
    if (control) declarationDraft[field.key] = control.value.trim();
  }
  const trailerCheckbox = declarationInfoForm.querySelector('[data-field="hasTrailer"]');
  if (trailerCheckbox) {
    declarationDraft.hasTrailer = trailerCheckbox.checked;
    if (!trailerCheckbox.checked) declarationDraft.trailerPlate = "";
  }
}

function bindMissingHighlight(control) {
  const sync = () => {
    const value = control.value.trim();
    control.classList.toggle("is-missing", !value || value === "-");
  };
  sync();
  control.addEventListener("input", sync);
  control.addEventListener("change", sync);
}

function appendGoodsField(card, labelText, fieldName, value, { type = "text", rows, options } = {}) {
  const label = document.createElement("label");
  const caption = document.createElement("span");
  caption.textContent = labelText;
  label.append(caption);

  let control;
  if (type === "textarea") {
    control = document.createElement("textarea");
    control.rows = rows ?? 3;
  } else if (type === "select") {
    control = document.createElement("select");
    for (const option of options ?? []) {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      control.append(node);
    }
  } else {
    control = document.createElement("input");
    control.type = "text";
  }

  if (control.tagName === "SELECT") {
    const current = inputValueFromDraft(value);
    if (current && ![...control.options].some((option) => option.value === current)) {
      const extra = document.createElement("option");
      extra.value = current;
      extra.textContent = current;
      control.insertBefore(extra, control.firstChild);
    }
  }
  control.value = inputValueFromDraft(value);
  control.dataset.field = fieldName;
  bindMissingHighlight(control);
  label.append(control);
  card.append(label);
  return control;
}

function renderGoodsForm() {
  goodsList.replaceChildren();

  for (const [i, item] of goodsDraft.entries()) {
    const card = document.createElement("article");
    card.className = "goods-card";
    card.dataset.index = String(item.index);

    const badge = document.createElement("span");
    badge.className = "goods-card-line-badge";
    badge.textContent = String(item.numeric || i + 1);
    card.append(badge);

    appendGoodsField(card, FILLED_GOODS_LABELS.quantity, "quantity", item.quantity);
    appendGoodsField(card, FILLED_GOODS_LABELS.quantityUnit, "quantityUnit", item.quantityUnit);
    appendGoodsField(card, FILLED_GOODS_LABELS.netWeight, "netWeight", item.netWeight);
    appendGoodsField(card, FILLED_GOODS_LABELS.grossWeight, "grossWeight", item.grossWeight);
    appendGoodsField(card, FILLED_GOODS_LABELS.invoicedCost, "invoicedCost", item.invoicedCost);
    appendGoodsField(card, FILLED_GOODS_LABELS.description, "description", item.description, {
      type: "textarea",
      rows: 3,
    });

    const codeInput = appendGoodsField(
      card,
      FILLED_GOODS_LABELS.tnvedCode,
      "tnvedCode",
      item.tnvedCode,
    );
    codeInput.placeholder = "Լրացրեք ԱՏԳ կոդը";

    appendGoodsField(card, FILLED_GOODS_LABELS.originCountry, "originCountry", item.originCountry, {
      type: "select",
      options: COUNTRY_CODE_OPTIONS,
    });
    appendGoodsField(card, FILLED_GOODS_LABELS.packageTypeCode, "packageTypeCode", item.packageTypeCode, {
      type: "select",
      options: PACKAGE_TYPE_OPTIONS,
    });
    appendGoodsField(card, FILLED_GOODS_LABELS.packingCode, "packingCode", item.packingCode, {
      type: "select",
      options: PACKING_CODE_OPTIONS,
    });

    for (const control of card.querySelectorAll("[data-field]")) {
      if (!isGoodsFieldFlagged(control.dataset.field, item.numeric, reviewItems)) continue;
      control.classList.add("is-flagged");
      control.title = goodsFieldFlagText(control.dataset.field, item.numeric, reviewItems);
    }

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "goods-delete-btn";
    deleteBtn.textContent = "Հեռացնել ապրանքը";
    deleteBtn.addEventListener("click", () => void deleteGoodsLine(item.index));
    card.append(deleteBtn);

    goodsList.append(card);
  }

  updateGoodsSearch({ reset: false, scroll: false });
  goodsSection.hidden = false;
}

function collectGoodsFromForm() {
  for (const card of goodsList.querySelectorAll(".goods-card")) {
    const index = Number(card.dataset.index);
    const item = goodsDraft.find((row) => row.index === index);
    if (!item) continue;
    for (const control of card.querySelectorAll("[data-field]")) {
      item[control.dataset.field] = control.value.trim();
    }
  }
}

function goodsCardHaystack(card) {
  const badge = card.querySelector(".goods-card-line-badge")?.textContent ?? "";
  const fields = [...card.querySelectorAll("[data-field]")].map((control) => control.value).join(" ");
  return `${badge} ${fields}`.toLowerCase();
}

function clearGoodsSearchHighlight() {
  for (const card of goodsList.querySelectorAll(".goods-card.is-search-hit")) {
    card.classList.remove("is-search-hit");
  }
}

function updateGoodsSearch({ reset = false, scroll = false } = {}) {
  const query = goodsSearchInput.value.trim().toLowerCase();
  clearGoodsSearchHighlight();
  if (!query) {
    goodsSearchHits = [];
    goodsSearchPos = -1;
    goodsSearchCount.textContent = "";
    return;
  }
  const hits = [...goodsList.querySelectorAll(".goods-card")].filter((card) =>
    goodsCardHaystack(card).includes(query),
  );
  if (/^\d+$/.test(query)) {
    const exact = hits.find(
      (card) => card.querySelector(".goods-card-line-badge")?.textContent === query,
    );
    goodsSearchHits = exact ? [exact, ...hits.filter((card) => card !== exact)] : hits;
  } else {
    goodsSearchHits = hits;
  }
  if (goodsSearchHits.length === 0) {
    goodsSearchPos = -1;
    goodsSearchCount.textContent = "0";
    return;
  }
  if (reset || goodsSearchPos < 0 || goodsSearchPos >= goodsSearchHits.length) goodsSearchPos = 0;
  const card = goodsSearchHits[goodsSearchPos];
  card.classList.add("is-search-hit");
  goodsSearchCount.textContent = `${goodsSearchPos + 1}/${goodsSearchHits.length}`;
  if (scroll) card.scrollIntoView({ behavior: "smooth", block: "center" });
}

goodsSearchInput.addEventListener("input", () => updateGoodsSearch({ reset: true, scroll: true }));
goodsSearchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && goodsSearchHits.length > 0) {
    event.preventDefault();
    goodsSearchPos = (goodsSearchPos + 1) % goodsSearchHits.length;
    updateGoodsSearch({ scroll: true });
  }
});

saveGoodsBtn.addEventListener("click", () => {
  if (!syncDraftIntoXml()) return;
  saveStatus.hidden = false;
  setTimeout(() => {
    saveStatus.hidden = true;
  }, 2000);
});

downloadXmlBtn.addEventListener("click", () => {
  if (!syncDraftIntoXml()) return;
  downloadBlob(result.xml, result.filename, "application/xml");
});

downloadExcelBtn.addEventListener("click", () => {
  if (!syncDraftIntoXml()) return;
  downloadBlob(
    goodsToExcelXlsx(declarationDraft, goodsDraft),
    excelFilenameFrom(result.filename),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  );
});

addGoodsBtn.addEventListener("click", () => {
  if (!syncDraftIntoXml()) return;
  result = { ...result, xml: addGoodsToXml(result.xml) };
  goodsDraft = parseFilledGoodsFromXml(result.xml);
  if (declarationDraft) declarationDraft.totalGoodsNumber = String(goodsDraft.length);
  renderGoodsForm();
  renderDeclarationInfo();
  syncDraftIntoXml();
});

async function deleteGoodsLine(index) {
  if (goodsDraft.length <= 1) return;
  const confirmed = await showConfirmDialog({
    message: "Համոզվա՞ծ եք, որ ուզում եք հեռացնել ապրանքը։",
    danger: true,
  });
  if (!confirmed) return;
  if (!syncDraftIntoXml()) return;
  result = { ...result, xml: removeGoodsFromXml(result.xml, index) };
  goodsDraft = parseFilledGoodsFromXml(result.xml);
  if (declarationDraft) declarationDraft.totalGoodsNumber = String(goodsDraft.length);
  renderGoodsForm();
  renderDeclarationInfo();
  syncDraftIntoXml();
}

function syncDraftIntoXml() {
  collectGoodsFromForm();
  collectDeclarationFromForm();
  if (!result) return false;
  result = {
    ...result,
    xml: updateDeclarationInXml(updateGoodsInXml(result.xml, goodsDraft), declarationDraft),
  };
  void saveWorkflow({
    phase: "edit",
    xml: result.xml,
    filename: result.filename,
    summary: result.summary,
    reviewReport: result.reviewReport,
  });
  return true;
}

function showConfirmDialog({ message, confirmText = "Այո", cancelText = "Ոչ", danger = false }) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";
    dialog.setAttribute("role", "alertdialog");
    dialog.setAttribute("aria-modal", "true");

    const text = document.createElement("p");
    text.className = "modal-message";
    text.textContent = message;

    const actions = document.createElement("div");
    actions.className = "modal-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "modal-btn modal-btn-cancel";
    cancelBtn.textContent = cancelText;

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = danger ? "modal-btn modal-btn-danger" : "modal-btn modal-btn-confirm";
    confirmBtn.textContent = confirmText;

    let settled = false;
    const close = (value) => {
      if (settled) return;
      settled = true;
      document.removeEventListener("keydown", onKey);
      backdrop.remove();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") close(false);
    };

    cancelBtn.addEventListener("click", () => close(false));
    confirmBtn.addEventListener("click", () => close(true));
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close(false);
    });
    document.addEventListener("keydown", onKey);

    actions.append(cancelBtn, confirmBtn);
    dialog.append(text, actions);
    backdrop.append(dialog);
    document.body.append(backdrop);
    cancelBtn.focus();
  });
}

function downloadBlob(content, filename, mediaType) {
  const url = URL.createObjectURL(new Blob([content], { type: mediaType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function hideResult() {
  result = null;
  declarationDraft = null;
  goodsDraft = [];
  reviewItems = [];
  summarySection.hidden = true;
  summaryNotes.hidden = true;
  declarationInfoSection.hidden = true;
  declarationInfoForm.replaceChildren();
  goodsSection.hidden = true;
  goodsList.replaceChildren();
}

function teardownRun() {
  stopPolling();
  activeJobId = null;
  hideResult();
  setState(STATE.IDLE);
}

async function startNewRun() {
  selectedFiles = [];
  pendingDocuments = [];
  await clearWorkflow();
  teardownRun();
  updateUi();
  fileZone.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setState(nextState, message) {
  state = nextState;
  const inProgress = nextState === STATE.LOADING || nextState === STATE.PROCESSING;
  progressSection.hidden = !inProgress;
  if (nextState === STATE.LOADING) updateProgress("queued", null);
  actionBtn.classList.remove("is-success", "is-error");
  actionBtn.replaceChildren();

  if (inProgress) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    actionBtn.append(spinner);
    actionBtn.append(
      document.createTextNode(
        nextState === STATE.LOADING ? "Ուղարկվում է…" : message || "Մշակվում է…",
      ),
    );
    actionBtn.disabled = true;
    newRunBtn.hidden = true;
    return;
  }

  if (nextState === STATE.EDIT) {
    actionBtn.append(document.createTextNode("Հայտարարագիրը պատրաստ է"));
    actionBtn.disabled = true;
    newRunBtn.hidden = false;
    return;
  }

  newRunBtn.hidden = true;

  if (nextState === STATE.ERROR) {
    actionBtn.classList.add("is-error");
    actionBtn.append(document.createTextNode(message ?? "Ձախողվեց"));
    actionBtn.disabled = false;
    return;
  }

  updateUi();
}

// What stops a run right now, or null when nothing does. Only the two things the service
// genuinely refuses: no files, and no token. The declarant profile is not among them —
// `SubmitRunRequest.profile` is optional and an unfilled field comes back as a review item.
function runBlocker() {
  if (selectedFiles.length < MIN_FILES) return "Ընտրեք ֆայլերը";
  if (!connection.hasToken) return "Լրացրեք թոքենը կարգավորումներում";
  return null;
}

function updateUi() {
  renderFileList();
  fileZoneLabelEl.textContent = selectedFiles.length > 0 ? "Ավելացնել ֆայլ" : "Ընտրեք ֆայլերը";

  const fileCount = selectedFiles.length;
  fileZone.classList.toggle("has-files", fileCount > 0);

  if (fileCount === 0) {
    fileHintEl.textContent =
      "Վերբեռնեք հաշիվ-ապրանքագիրը (և ЦМР-ը, եթե կա — կարող է լինել նաև մեկ PDF)";
    fileHintEl.hidden = false;
    fileCountEl.hidden = true;
  } else {
    fileHintEl.hidden = true;
    fileCountEl.hidden = false;
    fileCountEl.textContent = `Ընտրված է ${fileCount} ֆայլ`;
  }

  if (!isProfileComplete(profile)) {
    fileHintEl.textContent = "Լրացրեք դեկլարանտի տվյալները (👤)";
    fileHintEl.hidden = false;
  }

  if (state === STATE.IDLE) {
    actionBtn.disabled = Boolean(runBlocker());
  }
}
