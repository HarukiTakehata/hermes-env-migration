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
