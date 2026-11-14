# Review package Task 1
Base: a0aa5195de0806fe6f0bb7c163d0fd404f905882
Head: WORKING_TREE (no commit; user forbade commit)

## git status

 M mi_ai/console/static/app.js
 M mi_ai/console/static/index.html
?? .superpowers/
?? docs/superpowers/plans/
?? docs/superpowers/specs/2026-11-14-console-zh-labels-design.md

## git diff --stat

 mi_ai/console/static/app.js     | 53 +++++++++++++++++++++++++++++++++++------
 mi_ai/console/static/index.html |  2 +-
 2 files changed, 47 insertions(+), 8 deletions(-)

## git diff -U10

diff --git a/mi_ai/console/static/app.js b/mi_ai/console/static/app.js
index 0e5d6c9..30019f8 100644
--- a/mi_ai/console/static/app.js
+++ b/mi_ai/console/static/app.js
@@ -31,20 +31,59 @@ const CONFIG_GROUPS = [
       "MI_AI_LOG_KEEP_DAYS",
       "MI_AI_AUTH_CHECK_MINUTES",
       "MI_AI_CONSOLE",
       "MI_AI_CONSOLE_HOST",
       "MI_AI_CONSOLE_PORT",
       "CURSOR_API_KEY",
     ],
   },
 ];
 
+const CONFIG_LABELS = {
+  MI_USER: "小米账号",
+  MI_PASS: "小米密码",
+  OPENAI_API_KEY: "API 密钥",
+  OPENAI_API_BASE: "接口地址",
+  OPENAI_MODEL: "模型名",
+  KEYWORDS: "触发词",
+  PROMPT: "系统提示词",
+  START_CONVERSATION: "开始持续对话",
+  END_CONVERSATION: "结束持续对话",
+  HTTP_PROXY: "HTTP 代理",
+  VERBOSE: "日志详细程度",
+  LX06_DID: "设备 ID",
+  LX06_HARDWARE: "硬件型号",
+  LX06_MUTE_XIAOAI: "静音小爱",
+  LX06_STREAM: "流式播放",
+  LX06_USE_COMMAND: "使用指令模式",
+  L05C_DID: "设备 ID",
+  L05C_HARDWARE: "硬件型号",
+  L05C_MUTE_XIAOAI: "静音小爱",
+  L05C_STREAM: "流式播放",
+  L05C_USE_COMMAND: "使用指令模式",
+  MI_AI_DEVICES: "保活设备列表",
+  MI_AI_RESTART_BASE_SEC: "重启基础间隔（秒）",
+  MI_AI_RESTART_MAX_SEC: "重启最大间隔（秒）",
+  MI_AI_LOG_DIR: "日志目录",
+  MI_AI_LOG_KEEP_DAYS: "日志保留天数",
+  MI_AI_AUTH_CHECK_MINUTES: "鉴权检查间隔（分钟）",
+  MI_AI_CONSOLE: "控制台开关",
+  MI_AI_CONSOLE_HOST: "控制台主机",
+  MI_AI_CONSOLE_PORT: "控制台端口",
+  CURSOR_API_KEY: "Cursor API 密钥",
+};
+
+function labelZh(key) {
+  const zh = CONFIG_LABELS[key];
+  return zh ? `${key}（${zh}）` : key;
+}
+
 const SECRET_KEYS = new Set(["MI_PASS", "OPENAI_API_KEY", "CURSOR_API_KEY"]);
 const BOOL_KEYS = new Set([
   "LX06_MUTE_XIAOAI",
   "LX06_STREAM",
   "LX06_USE_COMMAND",
   "L05C_MUTE_XIAOAI",
   "L05C_STREAM",
   "L05C_USE_COMMAND",
 ]);
 
@@ -142,26 +181,26 @@ function renderOverview(data) {
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
-            hardware=${d.hardware || "—"} · did=${d.did || "未配置"}</p>
+            hardware（硬件型号）=${d.hardware || "—"} · did（设备 ID）=${d.did || "未配置"}</p>
           </div>
           <div class="flags">
-            <span class="flag ${d.stream ? "on" : ""}">stream ${d.stream ? "on" : "off"}</span>
-            <span class="flag ${d.use_command ? "on" : ""}">command ${d.use_command ? "on" : "off"}</span>
-            <span class="flag ${d.mute_xiaoai ? "on" : ""}">mute ${d.mute_xiaoai ? "on" : "off"}</span>
+            <span class="flag ${d.stream ? "on" : ""}">stream（流式播放） ${d.stream ? "on" : "off"}</span>
+            <span class="flag ${d.use_command ? "on" : ""}">command（指令模式） ${d.use_command ? "on" : "off"}</span>
+            <span class="flag ${d.mute_xiaoai ? "on" : ""}">mute（静音小爱） ${d.mute_xiaoai ? "on" : "off"}</span>
           </div>
         </article>`;
     })
     .join("");
 
   $("#dialog-block").innerHTML = `
     <div>触发词：<strong>${(dialog.keywords || []).join("、") || "—"}</strong></div>
     <div>持续对话：${dialog.start_conversation || "—"} / ${dialog.end_conversation || "—"}</div>
     <div>接口：${dialog.openai_api_base || "—"}</div>
     <p class="prompt">${escapeHtml(dialog.prompt || "")}</p>
@@ -181,36 +220,36 @@ function renderConfigForm(payload) {
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
-            <label for="cfg-${key}">${key}</label>
+            <label for="cfg-${key}">${labelZh(key)}</label>
             <select id="cfg-${key}" name="${key}">
               <option value="true" ${on ? "selected" : ""}>true</option>
               <option value="false" ${!on ? "selected" : ""}>false</option>
             </select>
           </div>`;
         }
         if (SECRET_KEYS.has(key)) {
           const present = Boolean(val);
           return `<div class="config-item${full}">
-            <label for="cfg-${key}">${key}${present ? "（已配置，留空表示不改）" : ""}</label>
+            <label for="cfg-${key}">${labelZh(key)}${present ? "（已配置，留空表示不改）" : ""}</label>
             <input id="cfg-${key}" name="${key}" type="password" value="" placeholder="${present ? escapeAttr(val) : ""}" autocomplete="new-password" />
           </div>`;
         }
         return `<div class="config-item${full}">
-          <label for="cfg-${key}">${key}</label>
+          <label for="cfg-${key}">${labelZh(key)}</label>
           <input id="cfg-${key}" name="${key}" type="text" value="${escapeAttr(val)}" autocomplete="off" />
         </div>`;
       })
       .join("");
     return `<div class="config-grid"><h3 class="section-title" style="grid-column:1/-1;margin-top:0.4rem">${group.title}</h3>${fields}</div>`;
   }).join("");
 }
 
 function escapeAttr(s) {
   return String(s).replaceAll('"', "&quot;");
diff --git a/mi_ai/console/static/index.html b/mi_ai/console/static/index.html
index 74f33c1..637c974 100644
--- a/mi_ai/console/static/index.html
+++ b/mi_ai/console/static/index.html
@@ -21,21 +21,21 @@
       <button type="button" class="tab" data-tab="config" role="tab" aria-selected="false">配置</button>
     </nav>
   </header>
 
   <main>
     <section id="panel-overview" class="panel is-active" role="tabpanel">
       <p class="lede">设备状态、提示词与运行摘要。默认仅本机可访问。</p>
 
       <div class="status-strip" id="status-strip">
         <div class="stat">
-          <span class="stat-label">watchdog</span>
+          <span class="stat-label">watchdog（保活进程）</span>
           <span class="stat-value" id="wd-state">—</span>
         </div>
         <div class="stat">
           <span class="stat-label">登录</span>
           <span class="stat-value" id="auth-state">—</span>
         </div>
         <div class="stat">
           <span class="stat-label">端口</span>
           <span class="stat-value" id="port-state">—</span>
         </div>
