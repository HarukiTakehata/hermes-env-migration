## Phase 1 — 旧环境盘点 + 软件包使用痕迹

- 旧 home/snapshot 目录清单：`.hermes/`、凭据目录、技能、工作区、venv 等。
- **系统软件包痕迹**（决定「针对恢复」清单）：
  - 旧 `.bash_history`：`apt install`/`npm`/`npx`/`uv`/`pip`/`ffmpeg`/`screen`/`gcc` 等命令痕迹；
  - 旧 venv 的 `site-packages` 列表（推断依赖栈）；
  - `node_modules`/`.npm`/`.npm-global`（旧机器 node 生态痕迹）；
  - 旧会话库工具调用统计：`select tool_name, count(*) from messages where session_id in
    (旧会话) group by tool_name`——旧机器实际用过的工具一目了然；
  - 快照里 `/var/log/apt`、`dpkg.log` 等（若有）。
- 区分**系统包**（包管理器安装 → 恢复目标）vs **用户态资产**（venv/.npm/源码仓库 → 不迁移，
  见 Phase 2 约束）。
- 凭据只列键名（.env/.profile/.ssh/.aws/.gnupg）；记忆文件；技能目录；cron/kanban 计数。
