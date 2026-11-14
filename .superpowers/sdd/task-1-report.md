# Task 1 报告：配置项与状态标签中文说明

## 状态

**DONE**

## 摘要

在本地管理控制台静态前端中为配置表单标签、概览页设备卡片与状态条补充 `英文（中文）` 展示，未改动后端 API 或 `.env` 键名。

## 修改文件

| 文件 | 变更 |
|------|------|
| `mi_ai/console/static/app.js` | 新增 `CONFIG_LABELS`、`labelZh`；`renderConfigForm` 三处 label；`renderOverview` 设备开关与元信息 |
| `mi_ai/console/static/index.html` | 概览状态条 `watchdog（保活进程）` |

## 实现对照（Brief Steps 1–5）

### Step 1：`CONFIG_LABELS` 与 `labelZh`

- 插入位置：`CONFIG_GROUPS` 闭合数组之后、`SECRET_KEYS` 之前。
- 映射键与 brief 中 31 项一致，覆盖 `CONFIG_GROUPS` 内全部配置键。
- `labelZh(key)`：有中文则返回 `` `${key}（${zh}）` ``，否则回退 `key`。

### Step 2：`renderConfigForm`

- 布尔字段 `<label>`：`${labelZh(key)}`（选项值仍为 `true` / `false`）。
- 密钥字段 `<label>`：`${labelZh(key)}${present ? "（已配置，留空表示不改）" : ""}`。
- 普通文本字段 `<label>`：`${labelZh(key)}`。

### Step 3：`renderOverview` 设备卡片

- 开关：`stream（流式播放）`、`command（指令模式）`、`mute（静音小爱）`，后缀 `on` / `off` 未改。
- 元信息：`hardware（硬件型号）=…`、`did（设备 ID）=…`。

### Step 4：`index.html`

- `<span class="stat-label">watchdog（保活进程）</span>`。

### Step 5：验收（静态 grep，无前端测试框架）

| 检查项 | 结果 |
|--------|------|
| `CONFIG_LABELS` 存在 | ✓ |
| `function labelZh` 存在 | ✓ |
| `renderConfigForm` 三处 `labelZh(key)` | ✓ |
| 无残留 `` `<label ...>${key}` ``（未包 labelZh） | ✓ |
| 设备三开关与 hardware/did 中文 | ✓ |
| `watchdog（保活进程）` | ✓ |

## 约束遵守

- 展示格式：`英文（中文）` / 设备开关为 `英文（中文） on|off`。
- 未修改 `.env` 键名、`/api/config`、`/api/status`。
- 未执行 `git commit`（用户规则 + Brief Step 6）。

## Commits

无（按 brief 与用户要求未提交）。

## 自检

- 与 brief 代码片段逐行对照：映射表、`labelZh` 逻辑、三处 label、设备 HTML、`watchdog` 文案均一致。
- 未添加「新增 xx」类修改说明注释；未引入额外依赖或测试套件。

## 建议人工复核（可选）

1. 浏览器打开控制台概览：确认设备开关与 watchdog 文案。
2. 配置页：各字段为 `KEY（中文）`；保存后标签仍正确。
3. 强刷缓存后再次确认静态资源已更新。

## 遗留 / 顾虑

无。

## 整分支终审修复（移除越界 auth refresh）

### 状态

**DONE**

### 操作

| 项 | 处理 |
|----|------|
| `mi_ai/console/app.py` | `git checkout HEAD -- mi_ai/console/app.py`（移除 `/api/auth/refresh` 与 `ensure_auth`） |
| `index.html` | `#btn-refresh` 文案恢复为 `刷新`；保留 `watchdog（保活进程）` |
| `app.js` | 删除 `refreshLoginStatus`；`#btn-refresh` 仅 `refreshStatus().catch(showError)`；保留 Task 1 中文标签 |

### 验证命令与结果

```text
git diff HEAD -- mi_ai/console/app.py
# （无输出，与 HEAD 一致）

rg "/api/auth/refresh" mi_ai/console/static
# （无匹配）

rg "labelZh|CONFIG_LABELS|stream（流式播放）|watchdog（保活进程）" mi_ai/console/static
# index.html: watchdog（保活进程）
# app.js: CONFIG_LABELS, labelZh, stream（流式播放）, renderConfigForm labelZh

rg "btn-refresh" -A2 mi_ai/console/static/app.js
# refreshStatus().catch(showError)
```