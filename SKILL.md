---
name: hermes-env-migration
description: "Migrate a Hermes install from an old home snapshot."
version: 2.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, migration, restore, state.db, sessions, merge, credentials, memories, ssh, git, skills, cleanup, packages, environment]
---

# Hermes 环境迁移通用流程（old home → new install）

## When to Use

Use when the user asks to restore/migrate data from a previous Hermes environment into the
current install — "恢复之前的会话数据/凭据/工作区", an old home snapshot or backup exists on
disk, or moving between machines/containers. Covers the FULL lifecycle: current-env inspection →
old-env inventory (incl. system package traces) → targeted migration plan → merge → SSH keys →
skill git repos → credential validation → cleanup. Generic; adapt paths/identities to the case.

## 核心概念（先读，别踩坑）

- **两个 home 别混淆**：`$HERMES_HOME`（通常 `~/.hermes`，Hermes 数据目录，由环境变量显式
  指向）vs 终端 shell 的 `$HOME`（容器里常被重定向到 `$HERMES_HOME/home`）。解析路径永远用
  `${HERMES_HOME:-...}` 和 `echo $HOME` 实测，绝不硬编码 `~`。
- **SSH 客户端按 passwd home 找密钥，不用 `$HOME`**：`getent passwd <user>` 的 home（如
  `/home/user`）才是 ssh 读取 `.ssh/config` 和默认密钥的位置；shell 的 `$HOME` 重定向对 ssh
  无效。`ssh -v -G github.com | grep -i "reading configuration"` 可确认实际读取路径。
  密钥权威位置放 passwd home 的 `.ssh/`，shell-home 的 `.ssh` 用软链指向它（一份私钥两边可用）。
- 旧 home 快照典型内容：`.hermes/`（state.db、memories/、.env、config.yaml、cron/、
  kanban.db、sessions/ 请求转储）、`.ssh/`、`.aws/`、`.gnupg/`、`.gitconfig`、`.profile`
  （常带 `export KEY=...` 凭据）、`.agents/skills/`（npx 式技能）。
- `~/.agents/skills/` **不会被 Hermes 自动加载**——技能必须放 `$HERMES_HOME/skills/<分类>/<名>/SKILL.md`。
- 旧 `.hermes/skills/` 可能整体缺失（技能被推到 GitHub）——先查 GitHub 再下结论。
- state.db = SQLite WAL，同一时刻一个写者；活网关持有写锁，外部合并用短事务即可。
- `.env` 新键对已运行的网关进程不生效（env 启动时载入），重启/新会话后才可用——明确告知用户。
- **用户可能中途自行重排快照**（改名 old-env-*、移动目录、写自己的辅助脚本）——每个阶段开始前
  重新 `ls` 核实路径，别假设上一步的路径还在。
- **容器/无 root 是常态**：系统软件包恢复不能 `apt install` 时，走用户态手段（见 Phase 2）。

## Verification

- [ ] Phase 0/1 输出：当前环境清单 + 旧环境包痕迹 + 针对性方案（三清单）已与用户确认
- [ ] state.db 备份存在；sessions/messages 计数 = 原数 + 导入数；quick_check ok；FTS 行数一致
- [ ] session_search 命中旧会话（标题非 NULL）；skills_list 数量增加
- [ ] .env 键数/格式/实测通过；.ssh/.gnupg/.aws 权限正确；ssh -T 与 git ls-remote 走 SSH 成功
- [ ] 技能仓库：单提交、当前身份、%G?=G、origin 正确；强推后 ls-remote == 本地 HEAD
- [ ] 用户确认后旧内容已清理；最终报告含遗留问题（含待恢复的系统包）


## 参考文件（按需加载，详情见 references/）
- `references/00-phase-0-当前环境充分检查-先于一切-只读.md` — Phase 0 — 当前环境充分检查（先于一切，只读）
- `references/01-phase-1-旧环境盘点-软件包使用痕迹.md` — Phase 1 — 旧环境盘点 + 软件包使用痕迹
- `references/02-phase-2-针对性迁移方案-基于-0-1-的信息先出方案-确认后执行.md` — Phase 2 — 针对性迁移方案（基于 0+1 的信息先出方案，确认后执行）
- `references/03-phase-3-合并执行-记忆-env-凭据目录-技能-state-db.md` — Phase 3 — 合并执行（记忆 → .env → 凭据目录 → 技能 → state.db）
- `references/04-phase-4-ssh-密钥就位.md` — Phase 4 — SSH 密钥就位
- `references/05-phase-5-技能-git-仓库恢复.md` — Phase 5 — 技能 git 仓库恢复
- `references/06-phase-6-凭据核验-实测有效性-不只查存在.md` — Phase 6 — 凭据核验（实测有效性，不只查存在）
- `references/07-phase-7-清理与收尾-确认后才删.md` — Phase 7 — 清理与收尾（确认后才删）
- `references/08-陷阱速查.md` — 陷阱速查
- `references/09-support-files.md` — Support Files