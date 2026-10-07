# KitPrep 中央厨房 BOM 备料

按菜品 BOM 展开订单行、合并同原料需求，对照库存计算缺料并生成备料单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:5000 |
| API | http://localhost:10100 |
| API 文档 | http://localhost:10100/docs |
| Postgres | localhost:5451 |

健康检查：`GET http://localhost:10100/api/health`

## 使用说明

1. 在「菜品」「BOM」维护中央厨房出品与用料树。
2. 在「订单」「库存」确认当日需求与现有库存；在库存页给原料勾选并保存**含敏**标记。
3. 在「订单」或「备料单」点「生成备料单」：按含敏标记把缺料拆成**主缺料贴**与**敏料专册**两本物理账（含敏行只进专册），同时按 `min(需求, 结存)` 记**占用**；**结存数字不变**（不扣账），可用 = 结存 − 占用。
4. 主贴/专册/占用同一事务，一起过或一起退；拆账不一致整次回滚并返回 409 `LEDGER_SPLIT_VIOLATION`（与结存够不够无关）。
5. 同参数重复或两个页面抢点生成返回同一套两本账（指纹幂等）；改标记后再生成出新单，旧单冻结不可改。未打含敏时专册为空、缺料全走主贴。
6. 在「缺料」分别查看两本账：shortage = need − stock（仅正数）。

> 占用跨多次生成累计（历史单冻结不释放），多次生成后「可用」可能为负，属预期；`occupation_lines` 保留每单占用明细。

## 开发与测试

```bash
docker compose exec api pytest -q
```

无 Docker 时可用内存 SQLite 跑测试：`cd backend && pytest -q`（并发行锁用例需设 `TEST_DATABASE_URL` 指向 Postgres）。

老卷升级：启动时自动 `create_all` 建新表并对 `ingredients`、`prep_runs` 做幂等 ALTER（`is_allergen`、`occupied_qty`、`fingerprint` 唯一索引），无需手工迁移。
