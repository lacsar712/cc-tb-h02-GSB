# 茶叶拼配审评台

审评员对一个拼配批次打香气、滋味、汤色。服务端按 0.3 / 0.5 / 0.2 加权，7 分及以上通过。提交后只替换表格里新的一行，不整页跳转。

这是制茶审评，不是菜谱，也不是饮食记录。

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3192 |
| 应用 | http://localhost:8192 |
| PostgreSQL | localhost:54392 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| taster | tea123456 | 可审评 |
| observer | look123456 | 只看 |

## 启动

```bash
cd projects/13-tea-blend-cupping
docker compose up --build
```

## 验收

1. taster 登录后看到春茶-A 通过、夏茶-C 不通过。
2. 再提交一组高分，新行出现在表头，页面不整页刷新。
3. observer 登录后没有提交表单。

## 自动化准入核对

`backend/verify_access.py` 用标准库跑完三条链路的端到端核对，并在有
`DATABASE_URL` 时直查 `COUNT(*)`：

- observer 首页不渲染交评表；直接 POST 交评接口（带/不带 HX 头）返回 403，碰壁后记录数不变；
- taster 交一笔够线分返回 200 的新行片段，记录数恰好 +1，新行在表头；
- 前端片段逻辑：仅 2xx 成功响应才插行，403 等失败响应绝不插行。

容器方式运行（核对服务在 `verify` profile 中，普通 `up` 不启动）：

```bash
docker compose --profile verify run --rm verify
```

