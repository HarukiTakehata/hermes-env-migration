## Support Files

- `scripts/merge_hermes_home.py` — 幂等合并脚本（记忆→.env→凭据目录→技能→state.db）。
- `scripts/reconnect_skill_repos.py` — 技能目录 git 重连 + 提交脚本。
- `references/state-db-merge.md` — state.db 合并详解（schema 差异/id 重映射/标题去重/FTS）。
- `references/state-db-merge-notes.md` — 实测 schema 漂移记录（v23→v25）。
- `references/github-skill-recovery.md` — 网络受限时从 GitHub 恢复技能（API tarball 法）。
- `/workspace/.secure-backup/`（权限 700）— 本机凭据安全备份卷（SSH 私钥、PAT 等）+ `restore_secure.sh` 一键恢复脚本；容器重建后先跑它，再排查「凭据缺失」类故障。
