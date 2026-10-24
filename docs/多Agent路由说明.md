# 多 Agent 口令路由

在现有 xiaogpt 桥接之上增加一层**可配置 Agent 注册表**：默认走云端大模型问答；口令点名时可交给 Cursor（本机 / Cloud）。

## 配置

1. 复制 `agents.example.yaml` → `agents.yaml`（仓库已带一份可改）
2. 在 `.env` 填写 `CURSOR_API_KEY`（[Cursor Dashboard](https://cursor.com/dashboard)）
3. `cursor-cloud` 默认 `enabled: false`；要用 Cloud 时改成 `true` 并填 `repos`
4. Cursor 默认模型为 Auto 路由：`model: auto-smart` + `optimize_for: balanced`（`cost` / `balanced` / `intelligence`）。需 Teams/Enterprise 且团队开通 Router；个人账号若不支持可改回 `composer-2.5`

```powershell
pip install cursor-sdk
python -m mi_ai agents list
```

## 口令示例

| 说法 | 效果 |
|------|------|
| 帮我今天天气怎么样 | `default`（通常是 chat） |
| 帮我让**编程助手**说一声你好 | Cursor 本机（推荐，ASR 稳） |
| 帮我用**写代码**执行修复登录 | 同上 |
| 帮我用编程助手在登录里执行改密码 | Cursor + 名为「登录」的聊天 |
| 帮我用云端编程助手执行开 PR | Cloud（需启用 `cursor-cloud`） |

> 小爱对英文 `cursor` 常听成别的词；`agents.yaml` 里已加中文别名与「科瑟/克瑟」等听写兜底。

试路由（不真正调用）：

```powershell
python -m mi_ai agents route "用cursor在登录里执行改一下密码校验"
```

## 指定某一个聊天

Cursor 侧用稳定的 `agent_id` 表示一场聊天（本机 `agent-…`，Cloud `bc-…`）。

**方式 A：写在 agents.yaml**

```yaml
cursor:
  chats:
    登录: agent-xxxxxxxx
```

**方式 B：命令绑定（写入 data/agent_chat_bindings.json）**

```powershell
python -m mi_ai agents bind cursor 登录 agent-xxxxxxxx
python -m mi_ai agents chats cursor
```

口令里第一次说「在登录里」且尚未绑定：会**新建**会话，并把新的 `agent_id` 自动绑到「登录」。之后再说「在登录里 / 继续登录」会 `Agent.resume` 同一场。

`resume_policy`：

- `last`：未点名聊天时续上一次本 Agent 会话
- `new`：未点名时每次新建

## 关掉某个通用 Agent

在 `agents.yaml` 把对应项 `enabled: false` 即可（例如关掉 Cloud）。禁用的 Agent **不会**参与别名匹配；若口令点到已禁用项，会回退到 `default` 并口头说明。

## 与音箱的关系

仍是：音箱 → 本机桥接 → 选中的后端。Cursor 跑完后只把**短摘要**交给小爱 TTS；完整过程在 Cursor / 终端里看。
