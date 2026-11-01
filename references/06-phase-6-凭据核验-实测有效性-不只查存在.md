## Phase 6 — 凭据核验（实测有效性，不只查存在）

- .env 键清单：缺失/为空检查；格式检查（token 前缀、hex 长度）；与旧文件哈希比对一致性
  （sha256 前缀即可，值不进上下文）。
- 实测端点（只打状态码）：GitHub `GET /user`（PAT）、Cloudflare
  `GET /client/v4/user/tokens/verify`、DeepSeek `GET /models`、NVIDIA `GET /v1/models`、
  S3/R2 endpoint 可达性（基础域 vs 专属域名可能不同——专属域连不通≠凭据无效）。
- 发现失效凭据：如实报告（可能是旧机器遗留的过期 token，与迁移无关），给出重新生成的指引；
  **失效值在各副本都一样，旧文件没有保留价值**。
- 权限终检：.ssh/.gnupg/.aws/.env。
