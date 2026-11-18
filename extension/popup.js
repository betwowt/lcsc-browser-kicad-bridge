"use strict";

const input = document.getElementById("part");
const button = document.getElementById("import");
const status = document.getElementById("status");
const ID = /C[1-9][0-9]{0,30}/i;

function parseId(value) {
  const match = ID.exec(value || "");
  return match ? match[0].toUpperCase() : null;
}

async function run() {
  const lcscId = parseId(input.value);
  if (!lcscId) {
    status.textContent = "未找到料号；请输入 C1688 这类编号或商品页链接。";
    return;
  }
  button.disabled = true;
  status.textContent = `正在导入 ${lcscId}…`;
  try {
    const response = await chrome.runtime.sendMessage({type: "import", lcscId});
    if (!response || !response.ok) throw new Error(response?.error || "扩展未返回响应。");
    status.textContent =
      `${lcscId} 已导入：${response.directory}\n` +
      `3D 模型：${response.has_3d ? "包含" : "未包含"}` +
      (response.already_present ? "\n（该元件已在工程中，未重复下载）" : "");
  } catch (error) {
    status.textContent = error.message || String(error);
  } finally {
    button.disabled = false;
  }
}

button.addEventListener("click", run);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") run();
});

chrome.storage.local.get({part: ""}).then((settings) => {
  if (settings.part) input.value = settings.part;
});
input.addEventListener("input", () => {
  chrome.storage.local.set({part: input.value});
});
