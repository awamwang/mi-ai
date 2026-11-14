# 管理控制台中文说明设计

日期：2026-11-14  
状态：已确认展示风格（选项 C）与实现方案 1

## 目标

为管理控制台中的英文配置项、状态标签与设备开关补充中文解释，降低对照 `.env` 时的理解成本。不改变任何环境变量键名与保存逻辑。

## 展示约定（选项 C）

- 配置项标签：`KEY（中文）`，例如 `LX06_MUTE_XIAOAI（静音小爱）`
- 状态条英文标签：同样格式，例如 `watchdog（保活进程）`
- 设备开关：英文名 + 括号中文，例如 `stream（流式播放）`；开关值保持 `on` / `off`
- 布尔下拉选项保持 `true` / `false`

## 实现方案

仅修改前端：

- 主要改动：`mi_ai/console/static/app.js`
- 必要微调：`mi_ai/console/static/index.html`（概览状态条 `watchdog` 标签）
- 不改后端 API、不改 `.env` 键名、不引入独立 i18n 模块

在 `app.js` 增加键名 → 中文映射表，渲染配置表单与设备卡片时套用 `labelZh(key)` / 设备开关固定文案。

## 文案映射

### 配置项

| 键 | 中文 |
|----|------|
| MI_USER | 小米账号 |
| MI_PASS | 小米密码 |
| OPENAI_API_KEY | API 密钥 |
| OPENAI_API_BASE | 接口地址 |
| OPENAI_MODEL | 模型名 |
| KEYWORDS | 触发词 |
| PROMPT | 系统提示词 |
| START_CONVERSATION | 开始持续对话 |
| END_CONVERSATION | 结束持续对话 |
| HTTP_PROXY | HTTP 代理 |
| VERBOSE | 日志详细程度 |
| LX06_DID / L05C_DID | 设备 ID |
| LX06_HARDWARE / L05C_HARDWARE | 硬件型号 |
| LX06_MUTE_XIAOAI / L05C_MUTE_XIAOAI | 静音小爱 |
| LX06_STREAM / L05C_STREAM | 流式播放 |
| LX06_USE_COMMAND / L05C_USE_COMMAND | 使用指令模式 |
| MI_AI_DEVICES | 保活设备列表 |
| MI_AI_RESTART_BASE_SEC | 重启基础间隔（秒） |
| MI_AI_RESTART_MAX_SEC | 重启最大间隔（秒） |
| MI_AI_LOG_DIR | 日志目录 |
| MI_AI_LOG_KEEP_DAYS | 日志保留天数 |
| MI_AI_AUTH_CHECK_MINUTES | 鉴权检查间隔（分钟） |
| MI_AI_CONSOLE | 控制台开关 |
| MI_AI_CONSOLE_HOST | 控制台主机 |
| MI_AI_CONSOLE_PORT | 控制台端口 |
| CURSOR_API_KEY | Cursor API 密钥 |

### 概览状态与设备开关

| 原文 | 展示 |
|------|------|
| watchdog | watchdog（保活进程） |
| stream | stream（流式播放） |
| command | command（指令模式） |
| mute | mute（静音小爱） |

设备元信息中的 `hardware=` / `did=` 可改为 `hardware（硬件型号）=` / `did（设备 ID）=`，与选项 C 一致。

## 非目标

- 不做完整中英切换 / i18n 框架
- 不把中文写进 `.env` 注释同步逻辑
- 不改服务启停、Cookie 工具等已有中文文案区域
- 不改布尔值与 on/off 的英文取值本身

## 验收

1. 配置页每个可编辑项标签为 `KEY（中文）`
2. 概览设备卡片三个开关为带中文说明的名称，值为 on/off
3. 概览 `watchdog` 带中文说明
4. 保存配置、刷新状态行为与改前一致
