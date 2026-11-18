"use strict";

const DEFAULT_ENDPOINT = "http://127.0.0.1:8737";
const REQUEST_TIMEOUT_MS = 180000;

function normalizeEndpoint(value) {
  const url = new URL(value || DEFAULT_ENDPOINT);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) ||
      url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("endpoint 必须是 http://127.0.0.1:端口 或 http://localhost:端口");
  }
  return url.origin;
}

async function handleRequest(message) {
  let endpoint = DEFAULT_ENDPOINT;
  let timeoutId;
  try {
    const settings = await chrome.storage.local.get({endpoint: DEFAULT_ENDPOINT, token: ""});
    endpoint = normalizeEndpoint(settings.endpoint);
    const controller = new AbortController();
    timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const importing = message.type === "import";
    const options = {method: importing ? "POST" : "GET", signal: controller.signal};
    if (importing) {
      options.headers = {"Content-Type": "application/json", "X-Bridge-Token": (settings.token || "").trim()};
      options.body = JSON.stringify({lcsc_id: message.lcscId});
    }
    let response;
    let payload;
    try {
      response = await fetch(`${endpoint}/${importing ? "import" : "health"}`, options);
      const body = await response.text();
      try {
        payload = JSON.parse(body);
      } catch {
        payload = {};
      }
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        payload = {};
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return {ok: false, error: "请求超时（180 秒），请查看本地服务日志后重试。", log: []};
      }
      return {ok: false, error: `无法连接本地服务 ${endpoint}，请先运行 bridge_server.py`, log: []};
    }
    const log = Array.isArray(payload.log) ? payload.log : [];
    if (response.status === 401) {
      return {ok: false, error: "本机服务要求 token：请在扩展选项中填入 config.json 的 token（默认留空）", log};
    }
    if (!response.ok || payload.ok === false) {
      return {ok: false, error: payload.error || `本地服务返回 HTTP ${response.status}`, log};
    }
    if (payload.ok !== true) {
      return {ok: false, error: "本地服务返回了无效响应，请检查 endpoint。", log};
    }
    return {ok: true, ...payload};
  } catch (error) {
    return {ok: false, error: error.message || String(error), log: []};
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId);
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !["import", "health"].includes(message.type)) {
    return false;
  }
  handleRequest(message).then(sendResponse, (error) => {
    sendResponse({ok: false, error: error.message || String(error), log: []});
  });
  // The asynchronous response keeps the MV3 message channel open.
  return true;
});
