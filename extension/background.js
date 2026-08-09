const DEFAULT_SERVER_URL = "http://127.0.0.1:8420";
// M15 v1's only auth is this one shared dev token (see .env.example SERVICE_DEV_TOKEN).
// Defaulting it here means opening the panel works with no options-page visit; anyone
// pointing the extension at a server with a different token still overrides it there.
const DEFAULT_SERVICE_TOKEN = "local-dev-only-change-me";

chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

void chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

const HANDLERS = {
  "get-connection": getConnection,
  "get-profile": getProfile,
  "save-profile": saveProfile,
  "submit-run": submitRun,
  "poll-run": pollRun,
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = HANDLERS[message?.type];
  if (!handler) return undefined;
  handler(message)
    .then((result) => sendResponse({ ok: true, ...result }))
    .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
  return true;
});

async function readConnection() {
  const { serverUrl, serviceToken } = await chrome.storage.local.get([
    "serverUrl",
    "serviceToken",
  ]);
  return {
    serverUrl: String(serverUrl || DEFAULT_SERVER_URL).replace(/\/+$/, ""),
    token: String(serviceToken || DEFAULT_SERVICE_TOKEN),
  };
}

async function getConnection() {
  const { serverUrl, token } = await readConnection();
  let reachable = false;
  let reason = null;
  try {
    const response = await fetch(`${serverUrl}/health`);
    reachable = response.ok;
    if (!reachable) reason = `${serverUrl}/health → ${response.status}`;
  } catch (error) {
    reason = error?.message || String(error);
  }
  return { connection: { serverUrl, hasToken: token.length > 0, reachable, reason } };
}

async function requireConnection() {
  const connection = await readConnection();
  if (!connection.token) {
    throw new Error("Թոքենը լրացված չէ — բացեք կարգավորումները");
  }
  return connection;
}

async function getProfile() {
  const { profile } = await chrome.storage.local.get("profile");
  return { profile: normalizeProfile(profile) };
}

async function saveProfile({ profile }) {
  const next = normalizeProfile(profile);
  await chrome.storage.local.set({ profile: next });
  return { profile: next };
}

function normalizeProfile(profile) {
  const text = (value) => String(value ?? "").trim();
  return {
    organizationName: text(profile?.organizationName),
    taxCode: text(profile?.taxCode),
    streetHouse: text(profile?.streetHouse),
    fillerSurname: text(profile?.fillerSurname),
    fillerGivenName: text(profile?.fillerGivenName),
  };
}

function toImporterProfile(profile) {
  const name = profile?.organizationName || null;
  const taxCode = profile?.taxCode || null;
  const streetHouse = profile?.streetHouse || null;
  if (!name && !taxCode && !streetHouse) return null;
  return { name, tax_code: taxCode, street_house: streetHouse };
}

function toFillerProfile(profile) {
  const surname = profile?.fillerSurname || "";
  const givenName = profile?.fillerGivenName || "";
  if (!surname || !givenName) return null;
  return { surname, given_name: givenName };
}

async function submitRun({ files, profile }) {
  const { serverUrl, token } = await requireConnection();
  const payload = (files ?? [])
    .filter((file) => file?.contentBase64)
    .map((file) => ({
      file_name: file.fileName,
      content_base64: file.contentBase64,
      declared_role: file.declaredRole ?? null,
    }));
  if (payload.length === 0) throw new Error("Ավելացրեք առնվազն մեկ ֆայլ");

  const importer = toImporterProfile(profile);
  const filler = toFillerProfile(profile);
  const body = {
    files: payload,
    profile: {
      ...(importer ? { importer } : {}),
      ...(filler ? { filler } : {}),
    },
  };

  const response = await request(serverUrl, token, "/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const submitted = await readJson(response);
  return { jobId: submitted.job_id };
}

async function pollRun({ jobId }) {
  const { serverUrl, token } = await requireConnection();
  const path = `/runs/${encodeURIComponent(jobId)}`;

  const statusResponse = await request(serverUrl, token, path);
  if (statusResponse.status === 404) {
    return { status: "failed", error: "Աշխատանքը չգտնվեց սերվերում" };
  }
  const status = await readJson(statusResponse);
  if (status.status !== "succeeded") {
    return {
      status: status.status,
      stage: status.current_stage ?? null,
      error: status.error ?? null,
    };
  }

  const result = await readJson(await request(serverUrl, token, `${path}/result`));
  return {
    status: "succeeded",
    stage: status.current_stage ?? null,
    declarationXml: result.declaration_xml,
    reviewReport: result.review_report ?? null,
    summary: result.summary ?? null,
  };
}

function request(serverUrl, token, path, options = {}) {
  return fetch(`${serverUrl}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.headers ?? {}) },
  });
}

async function readJson(response) {
  if (response.status === 401) {
    throw new Error("Թոքենը մերժվեց — ստուգեք կարգավորումները");
  }
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

async function readError(response) {
  try {
    const detail = (await response.json())?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || String(item)).join("; ");
    }
    if (detail?.message) return `${detail.code ?? "error"}: ${detail.message}`;
  } catch {
    void 0;
  }
  return `սերվերը վերադարձրեց ${response.status}`;
}
