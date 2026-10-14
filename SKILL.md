---
name: hermes-env-migration
description: "Migrate a Hermes install from an old home snapshot."
version: 2.1.0
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

## Phase 0 — 当前环境充分检查（先于一切，只读）

迁移开始前必须先摸清目标环境，方案才「针对性」：

- 主机/OS：`/etc/os-release`、`uname -a`、架构；**包管理器**（apt/dnf/apk/pacman/brew 等）。
- 用户与权限：`whoami` / `id`；`sudo -n true` 实测是否有 root；**容器检测**
  （`/.dockerenv`、`/proc/1/cgroup` 含 docker/containerd、rootfs 为 overlay）。
- 工具链现状（决定缺口清单）：python3/pip、node/npm、git、curl/wget、ffmpeg、jq、
  gcc/make/go、常用 CLI（free/uptime/ps 等 procps 类）。
- 网络连通性（pypi/github/目标 API 域），磁盘/内存余量。

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

## Phase 2 — 针对性迁移方案（基于 0+1 的信息先出方案，确认后执行）

交付一份针对该案例的方案，明确三类清单：

1. **要合并**：记忆 / 凭据 / 旧会话 / 技能 / 密钥（对应 Phase 3–6）。
2. **要恢复的包**：按当前包管理器的具体命令（如 `apt install nodejs npm ffmpeg jq`）；
   容器无 root 时的用户态手段：
   - 系统库：`apt-get download <pkg>` + `dpkg-deb -x` 到 `~/.local/...` + `LD_LIBRARY_PATH`
     （Debian 13 注意 t64 包名）；
   - 静态二进制到 `~/.local/bin`：ffmpeg（johnvansickle）、jq；
   - node：nvm 或官方 tarball 到用户目录；python 包：`pip install --user` / uv；
   - venv：能用 requirements 重建就重建；旧 venv 可激活复用则先验证。
3. **不迁移（避免迁移软件包）**：
   - venv / `.venv*`：不整目录复制，用 `pip freeze`/requirements 重建；
   - `.npm` / `node_modules` / `.npm-global`：重装，不搬缓存；
   - **已有 remote 且可达的源码仓库**：直接 `git clone` 或原地保留——绝不复制 `.git`
     对象库/工作树；判断「可达」用 `git ls-remote <origin> HEAD`；
   - 各类缓存（models_dev_cache、浏览器缓存等）：自动重建。

用 clarify 与用户确认方案后再进入执行阶段。

## Phase 3 — 合并执行（记忆 → .env → 凭据目录 → 技能 → state.db）

可复用 `scripts/merge_hermes_home.py`（幂等，参数在文件头）。规则：

1. **备份**：`state.db`、`.env` 带时间戳副本。
2. **记忆**：`MEMORY.md`/`USER.md` 复制进当前 `memories/`（有内容则合并）。
3. **.env 合并**：解析 `KEY=VALUE`，只追加当前缺失的键；旧 `.profile` 的 `export KEY=...` 一并
   并入。**值全程脚本内文件→文件搬运，绝不经过对话输出**（工具输出会被脱敏，别依赖回显）；
   输出只打键名。chmod 600。
4. **凭据目录**：`.ssh/.aws/.gnupg/.gitconfig` 复制到当前 home；权限：目录 700、私钥 600、
   `.pub` 644、`.env` 600、`.aws/credentials` 600 / `config` 644。
5. **技能**：`.agents/skills/<名>/` 复制到 `$HERMES_HOME/skills/<分类>/<名>/`（必须有 SKILL.md）。
6. **state.db 合并**（唯一高风险步骤，详见 `references/state-db-merge.md`）：
   - schema 差异：按**当前**列清单 INSERT，旧行缺失列补 NULL；messages 列集合需一致（assert）。
   - 消息 id 重映射：`cur_max + i`（INTEGER id 两库都从 1 开始）。
   - 标题回填：`sessions.title` 有**部分唯一索引**（`WHERE title IS NOT NULL`）——重复首条消息
     很常见，去重后缀用**完整会话 id + 计数器**，绝不用 `sid[:6]`（时间戳型 id 同日前缀相同），
     每条 UPDATE 单独 try/except，失败留 NULL。
   - FTS 三形态：先查 DDL。external-content → `INSERT INTO messages_fts(messages_fts)
     VALUES('rebuild')`；standalone+触发器 → 自动维护；standalone 无触发器 → 手动按当前列插行。
     ⚠️ standalone 上执行 rebuild 会清空索引。
   - 单事务 `BEGIN IMMEDIATE` + `PRAGMA busy_timeout=60000`；失败 rollback 保证幂等重跑。
   - 收尾：`PRAGMA quick_check` + 计数 + FTS `MATCH` 抽查。

## Phase 4 — SSH 密钥就位

1. 定位 ssh 实际读取路径（passwd home），把密钥/配置放到那里；shell-home `.ssh` 改软链。
2. `~/.ssh/config` 写 Host 专用块（User git、IdentityFile 绝对路径、IdentitiesOnly yes）。
3. 权限：`.ssh` 700、私钥 600、config 600、`.pub` 644。
4. 验证：`ssh -v -T git@github.com` 应出现 `Offering public key`；成功则 `git ls-remote
   git@github.com:<owner>/<repo>.git` 端到端确认。
5. **先查 GitHub 上是否已注册**：`GET /user/keys`（带 PAT）比对指纹（`ssh-keygen -lf`），
   已注册就不用让用户重复添加。
6. 无口令私钥才能非交互使用；`ssh-keygen -y -f <key>` 可检测是否带口令（会挂起）。

## Phase 5 — 技能 git 仓库恢复

- 快照缺 `skills/` 时：从 GitHub 恢复（git 协议被掐时用 API tarball 法）——
  见 `references/github-skill-recovery.md`。
- 下载/解压的技能目录没有 `.git`，按源仓库重连并重做提交（脚本 `scripts/reconnect_skill_repos.py`）：
  1. `git init -b main`；`git remote add origin <repo-url>`（源仓库未知用 GitHub API 探测；
     注意**私有仓库不在公开列表**，但带 PAT 的 tarball 能下载成功，别凭公开列表判断不存在）。
  2. 仓库级身份：user.name/email/signingkey/commit.gpgsign。
  3. **先测 GPG 非交互签名**：`echo test | timeout 20 gpg --batch --yes --sign
     --local-user <KEYID> --output /dev/null`——成功才 `git commit -S`，失败降级
     `git -c commit.gpgsign=false commit`。
  4. `git add -A && git commit -S`；验证 `git log --format=%G? -1` == `G`。
  5. 已复制到多处（如技能树）的目录：先 `diff -rq --exclude=.git A B` 确认一致，再
     `cp -a A/.git B/.git` 同步；**不要 rm 用户放置的目录**。
- **重置提交 + 强制推送**（用户要求时）：先 `git fetch origin <branch>` + `git diff --stat
  origin/<branch> HEAD`——树完全一致说明纯历史重写、零内容风险；`git push -u --force origin
  <branch>`（推送前用 API 确认远程默认分支）；推送后 `ls-remote` 比对远程 HEAD == 本地 HEAD。
  **只处理用户自己账号下的仓库**，第三方技能仓库（非用户账号）一律不碰。
- SSH 可用优先 SSH origin；未注册时用 HTTPS+PAT（脚本内读 token，不打印）。

## Phase 6 — 凭据核验（实测有效性，不只查存在）

- .env 键清单：缺失/为空检查；格式检查（token 前缀、hex 长度）；与旧文件哈希比对一致性
  （sha256 前缀即可，值不进上下文）。
- 实测端点（只打状态码）：GitHub `GET /user`（PAT）、Cloudflare
  `GET /client/v4/user/tokens/verify`、DeepSeek `GET /models`、NVIDIA `GET /v1/models`、
  S3/R2 endpoint 可达性（基础域 vs 专属域名可能不同——专属域连不通≠凭据无效）。
- 发现失效凭据：如实报告（可能是旧机器遗留的过期 token，与迁移无关），给出重新生成的指引；
  **失效值在各副本都一样，旧文件没有保留价值**。
- 权限终检：.ssh/.gnupg/.aws/.env。

## Phase 7 — 清理与收尾（确认后才删）

- **删除旧内容前先审计 + 用户确认**：核对所有有效凭据已迁移（哈希比对）、旧文件里没有
  .env/.ssh/.gnupg/.aws 之外的独有有效值，再 `rm -rf` 迁移残留（如 old-env-*、临时 tarball）。
- 用户可能想保留部分文件自行核对——给出选项，不要默认全删。
- 最终报告：恢复/验证/删除清单 + 遗留问题（失效凭据、旧路径映射、待恢复的包、待装技能）。

## 陷阱速查

1. HOME 重定向：shell `$HOME` ≠ passwd home；ssh 按 passwd home 找密钥（本流程最大的隐蔽坑）。
2. `sessions.title` 部分唯一索引：标题去重后缀用完整 sid + 计数器，逐行 try/except。
3. FTS 三种形态，standalone 上 rebuild 会清空索引。
4. 消息 id 冲突：重映射 `cur_max + i`；sqlite_sequence 自动更新。
5. 活网关 WAL：单事务短小 + busy_timeout，失败必 rollback。
6. .env/.profile 凭据值经过对话会被脱敏——脚本内搬运，只打键名。
7. 凭据重启网关后才生效；旧会话里的旧路径要映射到新位置。
8. 快照可能被用户中途改动——每阶段重新核实路径。
9. GPG 签名提交前先测非交互签名，避免 commit 挂起。
10. 强制推送前 diff 树一致性；只推用户自己账号的仓库。
11. **venv 是路径绑定的**：移动后 `bin/python` 软链与 `pyvenv.cfg` 的 home 指向旧路径——
    复制 venv 不如 `pip freeze` 重建；复用前先验证解释器能跑。重建时：
    - 从旧 venv 的 `site-packages/*.dist-info` 生成 `name==version`（别手工猜版本）；
    - **注意 Requires-Python 过滤**：旧 venv 可能基于更高 Python（如 3.13），其中的
      3.13 专用回填包（如 `audioop-lts`，3.12 stdlib 自带 audioop）在低版本下直接
      剔除；解析失败时从错误信息提取冲突包名自动剔除重试（循环 ≤10 轮）；
    - 验证用**正确的 import 名**（如 gitpython 的模块名是 `git`），且用真实工作文件
      实测（如 openpyxl 打开用户的总表 xlsx）；运行时依赖的系统二进制（如 pytesseract
      需要 tesseract 本体）单独检查并列入包恢复清单。
12. **有 remote 且可达的源码仓库不迁移**：`git ls-remote <origin> HEAD` 通就直接 clone/保留，
    复制 `.git` 对象库纯属浪费且易坏。
13. 容器无 root 恢复系统包：`apt-get download`+`dpkg-deb -x`+`LD_LIBRARY_PATH`、静态二进制到
    `~/.local/bin`、nvm/官方 tarball 装 node——先确认 `sudo -n true` 是否真的无权限。
    - `apt-cache depends --recurse` 的输出里**根包行没有缩进会被 grep 过滤掉**——根包
      （如 `tesseract-ocr`、`tesseract-ocr-chi-sim`）必须显式 `apt-get download`；
    - 运行时数据目录（如 `TESSDATA_PREFIX` 指向解压出的 tessdata）也要写进
      .bashrc/.profile，否则 tesseract 找不到语言包；
    - 用「ldd 无 not found + 真实渲染图 OCR」验证，不要只信二进制存在。

14. **快照里的 `.ssh` 可能是软链存根（本流程最易踩）**：旧环境 shell-home 的 `.ssh` 常软链到
    passwd home，快照若在不兼容的文件系统上打包，会把链接存成 `IntxLNK` 存根文件
    （几十字节，内容是 UTF-16 的目标路径）——**不是真实私钥**。恢复前先判定：
    `head -c 8 <key> | grep -q IntxLNK && echo 存根 || echo 真钥匙`（或看 `ssh-keygen -lf`）。
    真实私钥通常不在快照里，而在单独的安全备份（如持久卷上的备份目录）——先去那里找。
15. **凭据目录的查找根不同，别放错**：`git`/`gpg`/`aws` 都按 **`$HOME`**（shell home）查找
    `.gitconfig`/`.gnupg`/`.aws`；只有 **`ssh` 按 passwd home** 的 `.ssh`。
    - 复制 `.gnupg` 时**跳过 `S.gpg-agent*`**（旧遗留 unix socket，`shutil.copytree` 会报
      `[Errno 6] No such device or address`）；改用自写递归复制跳过 socket/软链。
    - `.gnupg` 目录需 700、内部文件 600，否则 gpg 报权限告警；AWS `credentials` 600、`config` 644。
    - 验证：`echo test | gpg --batch --yes --sign --local-user <KEYID> --output /dev/null`（签名）+
      `ssh -o BatchMode=yes -T git@github.com`（认证）。

## Support Files

- `scripts/merge_hermes_home.py` — 幂等合并脚本（记忆→.env→凭据目录→技能→state.db）。
- `scripts/reconnect_skill_repos.py` — 技能目录 git 重连 + 提交脚本。
- `references/state-db-merge.md` — state.db 合并详解（schema 差异/id 重映射/标题去重/FTS）。
- `references/state-db-merge-notes.md` — 实测 schema 漂移记录（v23→v25）。
- `references/github-skill-recovery.md` — 网络受限时从 GitHub 恢复技能（API tarball 法）。
- `/workspace/.secure-backup/`（权限 700）— 本机凭据安全备份卷（SSH 私钥、PAT 等）+ `restore_secure.sh` 一键恢复脚本；容器重建后先跑它，再排查「凭据缺失」类故障。

## Verification

- [ ] Phase 0/1 输出：当前环境清单 + 旧环境包痕迹 + 针对性方案（三清单）已与用户确认
- [ ] state.db 备份存在；sessions/messages 计数 = 原数 + 导入数；quick_check ok；FTS 行数一致
- [ ] session_search 命中旧会话（标题非 NULL）；skills_list 数量增加
- [ ] .env 键数/格式/实测通过；.ssh/.gnupg/.aws 权限正确；ssh -T 与 git ls-remote 走 SSH 成功
- [ ] 技能仓库：单提交、当前身份、%G?=G、origin 正确；强推后 ls-remote == 本地 HEAD
- [ ] 用户确认后旧内容已清理；最终报告含遗留问题（含待恢复的系统包）
