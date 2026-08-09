const DEFAULT_SERVER_URL = "http://127.0.0.1:8420";
// Mirrors background.js's DEFAULT_SERVICE_TOKEN — this file has no shared module to
// import it from (see background.js's comment for why it's hardcoded there).
const DEFAULT_SERVICE_TOKEN = "local-dev-only-change-me";

const serverUrlInput = document.getElementById("server-url");
const serviceTokenInput = document.getElementById("service-token");
const saveButton = document.getElementById("save");
const testButton = document.getElementById("test");
const statusEl = document.getElementById("status");

function isAlreadyPermitted(url) {
  return url.hostname === "127.0.0.1" || url.hostname === "localhost";
}

function showStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", Boolean(isError));
}

function readServerUrl() {
  const raw = serverUrlInput.value.trim() || DEFAULT_SERVER_URL;
  return { raw, normalized: raw.replace(/\/+$/, "") };
}

async function load() {
  const { serverUrl, serviceToken } = await chrome.storage.local.get([
    "serverUrl",
    "serviceToken",
  ]);
  serverUrlInput.value = serverUrl || DEFAULT_SERVER_URL;
  serviceTokenInput.value = serviceToken || DEFAULT_SERVICE_TOKEN;
}

async function save() {
  const { raw, normalized } = readServerUrl();

  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    showStatus("Server URL is not a valid URL.", true);
    return;
  }

  if (!isAlreadyPermitted(parsed)) {
    const granted = await chrome.permissions.request({ origins: [`${parsed.origin}/*`] });
    if (!granted) {
      showStatus(`Permission for ${parsed.origin} was not granted.`, true);
      return;
    }
  }

  const serviceToken = serviceTokenInput.value.trim();
  await chrome.storage.local.set({ serverUrl: normalized, serviceToken });
  showStatus(serviceToken ? "Saved." : "Saved, but the token is empty.", !serviceToken);
}

async function test() {
  const { normalized } = readServerUrl();
  const token = serviceTokenInput.value.trim();
  if (!token) {
    showStatus("Enter the service token first.", true);
    return;
  }
  testButton.disabled = true;
  try {
    const health = await fetch(`${normalized}/health`);
    if (!health.ok) {
      showStatus(`${normalized}/health returned ${health.status}.`, true);
      return;
    }
    const authed = await fetch(`${normalized}/runs/probe`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (authed.status === 401) {
      showStatus("Service is up, but the token was rejected.", true);
      return;
    }
    showStatus("Service is up and the token is accepted.", false);
  } catch (error) {
    showStatus(error?.message || String(error), true);
  } finally {
    testButton.disabled = false;
  }
}

saveButton.addEventListener("click", () => void save());
testButton.addEventListener("click", () => void test());
void load();
