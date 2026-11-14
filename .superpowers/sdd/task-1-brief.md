# Task 1 brief (from plan)

## Global Constraints

- 展示格式固定为 `英文（中文）`（选项 C）
- 布尔下拉仍为 `true` / `false`；设备开关值仍为 `on` / `off`
- 不改 `.env` 键名、不改 `/api/config` / `/api/status` 契约
- 中文注释；不主动添加「新增 xx」类修改说明注释
- 未经用户明确要求不执行 `git commit`

## File map

| 文件 | 职责 |
|------|------|
| `mi_ai/console/static/app.js` | 中文映射、`labelZh`、配置表单与设备卡片渲染 |
| `mi_ai/console/static/index.html` | 概览状态条 `watchdog` 标签文案 |

### Task 1: 配置项与状态标签中文说明

**Files:**
- Modify: `mi_ai/console/static/app.js`
- Modify: `mi_ai/console/static/index.html`

**Interfaces:**
- Produces: `CONFIG_LABELS`（`Record<string, string>`）、`labelZh(key: string): string`
- Consumes: 现有 `CONFIG_GROUPS`、`BOOL_KEYS`、`SECRET_KEYS`、`renderConfigForm`、`renderOverview`

- [ ] **Step 1: 在 `app.js` 顶部 `CONFIG_GROUPS` 之后加入映射与辅助函数**

```javascript
const CONFIG_LABELS = {
  MI_USER: "小米账号",
  MI_PASS: "小米密码",
  OPENAI_API_KEY: "API 密钥",
  OPENAI_API_BASE: "接口地址",
  OPENAI_MODEL: "模型名",
  KEYWORDS: "触发词",
  PROMPT: "系统提示词",
  START_CONVERSATION: "开始持续对话",
  END_CONVERSATION: "结束持续对话",
  HTTP_PROXY: "HTTP 代理",
  VERBOSE: "日志详细程度",
  LX06_DID: "设备 ID",
  LX06_HARDWARE: "硬件型号",
  LX06_MUTE_XIAOAI: "静音小爱",
  LX06_STREAM: "流式播放",
  LX06_USE_COMMAND: "使用指令模式",
  L05C_DID: "设备 ID",
  L05C_HARDWARE: "硬件型号",
  L05C_MUTE_XIAOAI: "静音小爱",
  L05C_STREAM: "流式播放",
  L05C_USE_COMMAND: "使用指令模式",
  MI_AI_DEVICES: "保活设备列表",
  MI_AI_RESTART_BASE_SEC: "重启基础间隔（秒）",
  MI_AI_RESTART_MAX_SEC: "重启最大间隔（秒）",
  MI_AI_LOG_DIR: "日志目录",
  MI_AI_LOG_KEEP_DAYS: "日志保留天数",
  MI_AI_AUTH_CHECK_MINUTES: "鉴权检查间隔（分钟）",
  MI_AI_CONSOLE: "控制台开关",
  MI_AI_CONSOLE_HOST: "控制台主机",
  MI_AI_CONSOLE_PORT: "控制台端口",
  CURSOR_API_KEY: "Cursor API 密钥",
};

function labelZh(key) {
  const zh = CONFIG_LABELS[key];
  return zh ? `${key}（${zh}）` : key;
}
```

- [ ] **Step 2: 修改 `renderConfigForm`，所有 `<label>` 使用 `labelZh(key)`**

把三处 `${key}` 标签改为 `${labelZh(key)}`（含布尔、密钥、普通输入）。密钥项后缀「（已配置，留空表示不改）」保留，接在中文说明之后，例如：

```javascript
<label for="cfg-${key}">${labelZh(key)}${present ? "（已配置，留空表示不改）" : ""}</label>
```

- [ ] **Step 3: 修改 `renderOverview` 设备卡片**

开关与元信息改为：

```javascript
<span class="flag ${d.stream ? "on" : ""}">stream（流式播放） ${d.stream ? "on" : "off"}</span>
<span class="flag ${d.use_command ? "on" : ""}">command（指令模式） ${d.use_command ? "on" : "off"}</span>
<span class="flag ${d.mute_xiaoai ? "on" : ""}">mute（静音小爱） ${d.mute_xiaoai ? "on" : "off"}</span>
```

```javascript
hardware（硬件型号）=${d.hardware || "—"} · did（设备 ID）=${d.did || "未配置"}
```

- [ ] **Step 4: 修改 `index.html` 状态条**

```html
<span class="stat-label">watchdog（保活进程）</span>
```

- [ ] **Step 5: 验收**

1. 打开控制台概览：设备三个开关与 `watchdog` 带中文说明；`on`/`off` 不变。
2. 打开配置页：每个字段为 `KEY（中文）`；保存后标签仍正确。
3. （可选）浏览器强刷缓存后复核。

- [ ] **Step 6: Commit（仅当用户明确要求时）** — **本次不要 commit**（用户未要求）。
