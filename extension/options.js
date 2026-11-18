"use strict";

const DEFAULT_ENDPOINT = "http://127.0.0.1:8737";
const form = document.getElementById("settings");
const endpointInput = document.getElementById("endpoint");
const tokenInput = document.getElementById("token");
const statusLine = document.getElementById("status");
const saveButton = document.getElementById("save");
const testButton = document.getElementById("test");

function errorText(error) {
  return error.message || String(error);
}

function normalizeToken(value) {
  let text = (value || "").trim().replace(/^['"]|['"]$/g, "").trim();
  const json = /"token"\s*:\s*"([^"]*)"/.exec(text);
  if (json) text = json[1];
  return text.trim();
}

async function saveSettings() {
  const url = new URL(endpointInput.value.trim() || DEFAULT_ENDPOINT);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) ||
      url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("请输入 http://127.0.0.1:端口 或 http://localhost:端口");
  }
  await chrome.storage.local.set({endpoint: url.origin, token: normalizeToken(tokenInput.value)});
  tokenInput.value = normalizeToken(tokenInput.value);
  endpointInput.value = url.origin;
}

function setBusy(busy) {
  saveButton.disabled = busy;
  testButton.disabled = busy;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    await saveSettings();
    statusLine.textContent = "已保存。";
  } catch (error) {
    statusLine.textContent = errorText(error);
  } finally {
    setBusy(false);
  }
});

testButton.addEventListener("click", async () => {
  setBusy(true);
  statusLine.textContent = "正在测试连接…";
  try {
    await saveSettings();
    const response = await chrome.runtime.sendMessage({type: "health"});
    if (!response || !response.ok) {
      throw new Error(response?.error || "扩展未返回响应。");
    }
    statusLine.textContent = JSON.stringify({
      ok: response.ok, project_dir: response.project_dir, token_required: response.token_required,
    }, null, 2) + (response.token_required && !normalizeToken(tokenInput.value)
      ? "\n本机服务启用了 token，请在下方填写 config.json 中的 token。"
      : "\n连接正常，可直接在商品页点击导入。");
  } catch (error) {
    statusLine.textContent = errorText(error);
  } finally {
    setBusy(false);
  }
});

async function loadSettings() {
  setBusy(true);
  try {
    const settings = await chrome.storage.local.get({endpoint: DEFAULT_ENDPOINT, token: ""});
    endpointInput.value = settings.endpoint;
    tokenInput.value = settings.token;
  } catch (error) {
    statusLine.textContent = errorText(error);
  } finally {
    setBusy(false);
  }
}

loadSettings();
