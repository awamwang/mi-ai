# mi-ai 本机控制台设计

日期：2026-11-07

## 目标

为本项目提供本机 Web 控制台：查看设备状态与基础配置，在页面修改 `.env`，并用 Cookie 工具把浏览器整段 Cookie 写入 token（方案 A）。

## 约束

- 仅绑定 `127.0.0.1`，默认端口 **18865**（8765 被占用；18765 在本机被 Windows 排除）
- Cookie 工具写入 `data/mi.token` + 种子，**不写** `MI_COOKIE`
- 敏感字段展示脱敏；保存配置时按白名单更新 `.env` 并尽量保留注释

## 形态

- 入口：`python -m mi_ai console` / `python -m mi_ai.console`
- FastAPI + 静态前端（概览 / 配置）
- 启停服务调用现有 `scripts/service-*.ps1`

## 非目标（首版）

公网访问、登录鉴权、agents.yaml 编辑、实时日志流
