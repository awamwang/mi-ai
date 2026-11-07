const $ = (sel) => document.querySelector(sel);

const CONFIG_GROUPS = [
  {
    title: "小米账号",
    keys: ["MI_USER", "MI_PASS"],
  },
  {
    title: "大模型",
    keys: ["OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL"],
  },
  {
    title: "对话",
    keys: ["KEYWORDS", "PROMPT", "START_CONVERSATION", "END_CONVERSATION", "HTTP_PROXY", "VERBOSE"],
  },
  {
    title: "LX06",
    keys: ["LX06_DID", "LX06_HARDWARE", "LX06_MUTE_XIAOAI", "LX06_STREAM", "LX06_USE_COMMAND"],
  },
  {
    title: "L05C",
    keys: ["L05C_DID", "L05C_HARDWARE", "L05C_MUTE_XIAOAI", "L05C_STREAM", "L05C_USE_COMMAND"],
  },
  {
    title: "保活 / 控制台 / Cursor",
    keys: [
      "MI_AI_DEVICES",
      "MI_AI_RESTART_BASE_SEC",
      "MI_AI_RESTART_MAX_SEC",
      "MI_AI_LOG_DIR",
      "MI_AI_LOG_KEEP_DAYS",
      "MI_AI_AUTH_CHECK_MINUTES",
      "MI_AI_CONSOLE",
      "MI_AI_CONSOLE_HOST",
      "MI_AI_CONSOLE_PORT",
      "CURSOR_API_KEY",
    ],
  },
];

const SECRET_KEYS = new Set(["MI_PASS", "OPENAI_API_KEY", "CURSOR_API_KEY"]);
const BOOL_KEYS = new Set([
  "LX06_MUTE_XIAOAI",
  "LX06_STREAM",
  "LX06_USE_COMMAND",
  "L05C_MUTE_XIAOAI",
  "L05C_STREAM",
  "L05C_USE_COMMAND",
]);

let configSnapshot = {};

function pill(ok, label) {
  const cls = ok === true ? "ok" : ok === false ? "bad" : "warn";
  return `<span class="stat-value"><span class="dot ${cls}"></span>${label}</span>`;
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || data.message || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function renderOverview(data) {
  const wd = data.watchdog || {};
  $("#wd-state").innerHTML = pill(
    !!wd.running,
    wd.running ? `运行中 pid=${wd.pid}` : "未运行"
  );

  const auth = data.auth || {};
  const state = auth.login_state || "";
  const authOk =
    state === "ok" ? true : state === "need_human" || state === "missing" ? false : null;
  $("#auth-state").innerHTML = pill(authOk, auth.login_label || "未知");

  const detailParts = [];
  if (auth.mi_user_masked) detailParts.push(`账号 ${auth.mi_user_masked}`);
  if (auth.user_id_masked) detailParts.push(`userId ${auth.user_id_masked}`);
  detailParts.push(auth.has_micoapi ? "micoapi ✓" : "micoapi ✗");
  detailParts.push(auth.has_xiaomiio ? "xiaomiio ✓" : "xiaomiio ✗");
  detailParts.push(auth.seed_exists ? "种子 ✓" : "种子 ✗");
  if (auth.auth_required && auth.auth_message) {
    detailParts.push(auth.auth_message.split("\n")[0]);
  }
  $("#login-detail").textContent = detailParts.join(" · ");

  const verifyBtn = $("#btn-open-verify");
  if (auth.notification_url) {
    verifyBtn.hidden = false;
    verifyBtn.dataset.url = auth.notification_url;
  } else {
    verifyBtn.hidden = true;
    delete verifyBtn.dataset.url;
  }
  $("#btn-open-login").dataset.url = auth.login_page_url || "https://account.xiaomi.com";

  const consoleInfo = data.console || {};
  const selfLink = $("#link-console-self");
  if (consoleInfo.url) {
    selfLink.href = consoleInfo.url;
    selfLink.textContent = consoleInfo.url;
  }

  const dialog = data.dialog || {};
  $("#model-state").textContent = dialog.openai_model || "—";

  const list = $("#device-list");
  list.innerHTML = (data.devices || [])
    .map((d) => {
      const state = d.running
        ? `<span class="dot ok"></span>运行中${d.pid ? ` · ${d.pid}` : ""}`
        : `<span class="dot bad"></span>未运行`;
      const managed = d.managed === false ? "（未纳入保活）" : "";
      return `
        <article class="device">
          <div>
            <h3 class="device-name">${d.name}</h3>
            <p class="device-meta">${state} ${managed}<br/>
            hardware=${d.hardware || "—"} · did=${d.did || "未配置"}</p>
          </div>
          <div class="flags">
            <span class="flag ${d.stream ? "on" : ""}">stream ${d.stream ? "on" : "off"}</span>
            <span class="flag ${d.use_command ? "on" : ""}">command ${d.use_command ? "on" : "off"}</span>
            <span class="flag ${d.mute_xiaoai ? "on" : ""}">mute ${d.mute_xiaoai ? "on" : "off"}</span>
          </div>
        </article>`;
    })
    .join("");

  $("#dialog-block").innerHTML = `
    <div>触发词：<strong>${(dialog.keywords || []).join("、") || "—"}</strong></div>
    <div>持续对话：${dialog.start_conversation || "—"} / ${dialog.end_conversation || "—"}</div>
    <div>接口：${dialog.openai_api_base || "—"}</div>
    <p class="prompt">${escapeHtml(dialog.prompt || "")}</p>
  `;
  $("#clock").textContent = data.time || "";
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderConfigForm(payload) {
  const values = payload.values || {};
  configSnapshot = { ...values };
  const form = $("#config-form");
  form.innerHTML = CONFIG_GROUPS.map((group) => {
    const fields = group.keys
      .map((key) => {
        const val = values[key] ?? "";
        const full = key === "PROMPT" || key === "KEYWORDS" ? " full" : "";
        if (BOOL_KEYS.has(key)) {
          const on = String(val).toLowerCase() === "true";
          return `<div class="config-item${full}">
            <label for="cfg-${key}">${key}</label>
            <select id="cfg-${key}" name="${key}">
              <option value="true" ${on ? "selected" : ""}>true</option>
              <option value="false" ${!on ? "selected" : ""}>false</option>
            </select>
          </div>`;
        }
        if (SECRET_KEYS.has(key)) {
          const present = Boolean(val);
          return `<div class="config-item${full}">
            <label for="cfg-${key}">${key}${present ? "（已配置，留空表示不改）" : ""}</label>
            <input id="cfg-${key}" name="${key}" type="password" value="" placeholder="${present ? escapeAttr(val) : ""}" autocomplete="new-password" />
          </div>`;
        }
        return `<div class="config-item${full}">
          <label for="cfg-${key}">${key}</label>
          <input id="cfg-${key}" name="${key}" type="text" value="${escapeAttr(val)}" autocomplete="off" />
        </div>`;
      })
      .join("");
    return `<div class="config-grid"><h3 class="section-title" style="grid-column:1/-1;margin-top:0.4rem">${group.title}</h3>${fields}</div>`;
  }).join("");
}

function escapeAttr(s) {
  return String(s).replaceAll('"', "&quot;");
}

async function refreshStatus() {
  const data = await fetchJson("/api/status");
  renderOverview(data);
}

async function refreshConfig() {
  const data = await fetchJson("/api/config");
  renderConfigForm(data);
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      document.querySelectorAll(".panel").forEach((p) => {
        const on = p.id === `panel-${tab}`;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
      });
      if (tab === "config") refreshConfig().catch(showError);
    });
  });
}

function showError(err) {
  const hint = $("#config-hint");
  if (hint) {
    hint.textContent = err.message || String(err);
    hint.classList.add("error");
  }
  console.error(err);
}

async function runService(action) {
  const out = $("#service-output");
  out.hidden = false;
  out.textContent = `执行 ${action}…`;
  const data = await fetchJson("/api/service", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  out.textContent = data.output || `(exit ${data.code})`;
  if (data.status) renderOverview(data.status);
  else await refreshStatus();
}

function setupActions() {
  $("#btn-refresh").addEventListener("click", () => {
    refreshStatus().catch(showError);
  });
  $("#btn-start").addEventListener("click", () => {
    runService("start").catch(showError);
  });
  $("#btn-stop").addEventListener("click", () => {
    runService("stop").catch(showError);
  });
  $("#btn-open-login").addEventListener("click", () => {
    const url = $("#btn-open-login").dataset.url || "https://account.xiaomi.com";
    window.open(url, "_blank", "noopener,noreferrer");
  });
  $("#btn-open-verify").addEventListener("click", () => {
    const url = $("#btn-open-verify").dataset.url;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  });

  $("#btn-cookie").addEventListener("click", async () => {
    const hint = $("#cookie-hint");
    hint.classList.remove("error");
    hint.textContent = "处理中…";
    try {
      const data = await fetchJson("/api/cookie", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cookie: $("#cookie-input").value,
          login: $("#cookie-login").checked,
        }),
      });
      let msg = data.message;
      if (data.login) {
        msg += data.login.ok ? "；换票成功。" : `；换票失败：\n${data.login.output || ""}`;
      }
      hint.textContent = msg;
      if (data.login && !data.login.ok) hint.classList.add("error");
      await refreshStatus();
    } catch (err) {
      hint.textContent = err.message || String(err);
      hint.classList.add("error");
    }
  });

  $("#config-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const hint = $("#config-hint");
    hint.classList.remove("error");
    const fd = new FormData(e.target);
    const values = {};
    for (const [k, v] of fd.entries()) values[k] = String(v);
    hint.textContent = "保存中…";
    try {
      const data = await fetchJson("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      hint.textContent = data.written?.length
        ? `已写入：${data.written.join(", ")}`
        : "没有需要更新的项";
      renderConfigForm({ values: data.values });
    } catch (err) {
      hint.textContent = err.message || String(err);
      hint.classList.add("error");
    }
  });
}

setupTabs();
setupActions();
refreshStatus().catch(showError);
