(() => {
  "use strict";

  const DETAIL_BUTTON_ID = "lcsc-kicad-bridge-import";
  const TOAST_ID = "lcsc-kicad-bridge-toast";
  const ID = /^C[1-9][0-9]{0,30}$/;
  const ROW_SELECTOR = 'section[data-spm="zy"]';
  let lastUrl;
  let currentId = null;
  let toastTimer;

  const text = (node) => (node?.textContent || "").replace(/[\s:：]/g, "");

  function productIdFromUrl() {
    let url;
    try {
      url = new URL(location.href);
    } catch {
      return null;
    }
    const match = /(?:^|_)(C[1-9][0-9]{0,30})\.html$/i.exec(url.pathname);
    return match ? match[1].toUpperCase() : null;
  }

  function productIdFromJsonLd() {
    let current;
    try {
      current = new URL(location.href);
    } catch {
      return null;
    }
    const found = new Set();
    const inspect = (value) => {
      if (!value || typeof value !== "object") return;
      if (Array.isArray(value)) {
        value.forEach(inspect);
        return;
      }
      if (Array.isArray(value["@graph"])) value["@graph"].forEach(inspect);
      const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"]];
      if (!types.includes("Product")) return;
      const address = value.url || value["@id"];
      if (typeof address !== "string") return;
      try {
        const product = new URL(address, current.href);
        if (product.origin !== current.origin || product.pathname !== current.pathname) return;
      } catch {
        return;
      }
      const sku = typeof value.sku === "string" ? value.sku.trim().toUpperCase() : "";
      if (ID.test(sku)) found.add(sku);
    };
    document.querySelectorAll('script[type="application/ld+json"]').forEach((script) => {
      try {
        inspect(JSON.parse(script.textContent));
      } catch {
        /* Broken JSON-LD must not break the page. */
      }
    });
    return found.size === 1 ? [...found][0] : null;
  }

  function currentProductId() {
    return productIdFromUrl() || productIdFromJsonLd();
  }

  function toast(message) {
    clearTimeout(toastTimer);
    document.getElementById(TOAST_ID)?.remove();
    const element = document.createElement("div");
    element.id = TOAST_ID;
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
    element.textContent = message;
    element.style.cssText =
      "position:fixed;right:24px;bottom:84px;z-index:2147483001;max-width:min(420px,calc(100vw - 48px));" +
      "padding:12px 16px;border-radius:8px;background:#172033;color:#fff;font:14px/1.5 sans-serif;" +
      "box-shadow:0 4px 16px #0005;white-space:pre-wrap;overflow-wrap:anywhere;";
    document.body.appendChild(element);
    toastTimer = setTimeout(() => element.remove(), 8000);
  }

  async function importPart(button, lcscId, busyLabel) {
    const idle = button.dataset.idleLabel || button.textContent;
    button.disabled = true;
    button.textContent = busyLabel;
    try {
      const response = await chrome.runtime.sendMessage({type: "import", lcscId});
      if (!response || !response.ok) {
        throw new Error(response?.error || "扩展未返回响应，请重试。");
      }
      button.textContent = "已导入";
      toast(`${lcscId} 已导入 KiCad；${response.has_3d ? "包含 3D 模型" : "未包含 3D 模型"}。`);
      setTimeout(() => {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = idle;
        }
      }, 3000);
    } catch (error) {
      const message = error.message || String(error);
      button.textContent = "导入失败";
      button.disabled = false;
      toast(
        message.includes("Extension context invalidated")
          ? "扩展已更新，请刷新页面"
          : message,
      );
    }
  }

  function detailButton() {
    const existing = document.getElementById(DETAIL_BUTTON_ID);
    const lcscId = currentProductId();
    if (lcscId === currentId && existing) return;
    existing?.remove();
    currentId = lcscId;
    if (!lcscId) return;
    const button = document.createElement("button");
    button.id = DETAIL_BUTTON_ID;
    button.type = "button";
    button.textContent = "导入 KiCad";
    button.dataset.idleLabel = "导入 KiCad";
    button.title = `将 ${lcscId} 导入本地 KiCad 工程`;
    button.style.cssText =
      "position:fixed;right:24px;bottom:24px;z-index:2147483000;padding:12px 20px;" +
      "border:1px solid #fff;border-radius:8px;background:#0759b5;color:#fff;" +
      "font:600 15px/1.4 sans-serif;box-shadow:0 3px 12px #0004;cursor:pointer;";
    button.addEventListener("click", () => importPart(button, lcscId, "导入中…"));
    document.body.appendChild(button);
  }

  function rowId(row) {
    let id = null;
    for (const entry of row.querySelectorAll("dl")) {
      const term = text(entry.querySelector("dt"));
      if (term !== "编号") continue;
      const value = (entry.querySelector("dd")?.textContent || "").trim().toUpperCase();
      if (!ID.test(value)) continue;
      if (id && id !== value) return null;
      id = value;
    }
    if (!id) return null;
    for (const node of row.querySelectorAll("[data-custom-data]")) {
      let info;
      try {
        info = JSON.parse(node.getAttribute("data-custom-data"));
      } catch {
        continue;
      }
      const code = typeof info?.productCode === "string" ? info.productCode.trim().toUpperCase() : "";
      if (code && code !== id) return null;
    }
    return id;
  }

  function rowButtons() {
    for (const row of document.querySelectorAll(ROW_SELECTOR)) {
      const lcscId = rowId(row);
      if (!lcscId) continue;
      const anchor = row.querySelector("[data-lcsc-kicad-bridge-row]");
      if (anchor?.isConnected && anchor.dataset.lcscKicadBridgeRow === lcscId) continue;
      anchor?.remove();
      const holder = [...row.querySelectorAll("dl")].find(
        (entry) => text(entry.querySelector("dt")) === "编号",
      );
      if (!holder) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.lcscKicadBridgeRow = lcscId;
      button.textContent = "导入";
      button.dataset.idleLabel = "导入";
      button.title = `将 ${lcscId} 导入本地 KiCad 工程`;
      button.style.cssText =
        "display:block;width:100%;margin-top:6px;padding:6px 0;border:0;border-radius:4px;" +
        "background:#0759b5;color:#fff;font:600 13px/1.4 sans-serif;cursor:pointer;";
      button.addEventListener("click", () => importPart(button, lcscId, "导入中…"));
      // Prefer the row's right-hand action column, just above the sales note.
      const note = [...row.querySelectorAll("p")].find((node) =>
        (node.textContent || "").includes("近期成交"),
      );
      const column = note?.parentElement;
      if (column) {
        column.insertBefore(button, note);
      } else {
        holder.insertAdjacentElement("afterend", button);
      }
    }
  }

  function scan() {
    if (!document.body) return;
    if (lastUrl !== location.href) {
      lastUrl = location.href;
      currentId = null;
      document.getElementById(DETAIL_BUTTON_ID)?.remove();
    }
    detailButton();
    rowButtons();
  }

  // A repeated injection must not create a second interval or stale button.
  const marker = "data-lcsc-kicad-bridge-active";
  if (!document.documentElement.hasAttribute(marker)) {
    document.documentElement.setAttribute(marker, "true");
    scan();
    setInterval(scan, 800);
  }
})();
