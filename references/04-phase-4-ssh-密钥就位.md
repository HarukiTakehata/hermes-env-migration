## Phase 4 — SSH 密钥就位

1. 定位 ssh 实际读取路径（passwd home），把密钥/配置放到那里；shell-home `.ssh` 改软链。
2. `~/.ssh/config` 写 Host 专用块（User git、IdentityFile 绝对路径、IdentitiesOnly yes）。
3. 权限：`.ssh` 700、私钥 600、config 600、`.pub` 644。
4. 验证：`ssh -v -T git@github.com` 应出现 `Offering public key`；成功则 `git ls-remote
   git@github.com:<owner>/<repo>.git` 端到端确认。
5. **先查 GitHub 上是否已注册**：`GET /user/keys`（带 PAT）比对指纹（`ssh-keygen -lf`），
   已注册就不用让用户重复添加。
6. 无口令私钥才能非交互使用；`ssh-keygen -y -f <key>` 可检测是否带口令（会挂起）。
