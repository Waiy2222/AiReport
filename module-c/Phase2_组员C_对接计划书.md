# Phase 2 组员C — 项目对接计划书

> 日期：2026-05-28
> 状态：全部完成

---

## 一、本次完成的任务

### 功能实现

| 功能 | 文件 | 状态 |
|------|------|------|
| 公众号消息回调（签名验证、异步处理） | `backend/weixin_oa.py` | ✅ |
| 标签 CRUD API + 用户行为追踪 + 用户画像 | `backend/tags.py` | ✅ |
| 按用户标签个性化推送 | `backend/push.py` | ✅ |
| 公众号配置项 | `backend/config.py` | ✅ |
| 新增数据模型 | `backend/models.py` | ✅ |
| 标签和行为假数据 | `backend/mock_data.py` | ✅ |
| 注册所有新路由 | `backend/main.py` | ✅ |
| H5 标签选择页 | `h5/preferences.html` | ✅ |

### 新增接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/weixin/callback` | 微信服务器验证 |
| POST | `/weixin/callback` | 微信消息回调（异步） |
| GET | `/api/tags` | 可用标签列表 |
| GET | `/api/user/preferences` | 获取用户偏好 |
| POST | `/api/user/preferences` | 设置用户偏好 |
| GET | `/api/user/{openid}/profile` | 用户画像 |
| POST | `/api/behavior` | 上报用户行为 |
| POST | `/push` | 个性化推送（支持 type 参数） |

### 测试

| 测试文件 | 测试数 | 通过 |
|----------|--------|------|
| `tests/test_weixin_oa.py` | 20 | 20 ✅ |
| `tests/test_tags.py` | 12 | 12 ✅ |
| `tests/test_push_v2.py` | 11 | 11 ✅ |
| **合计** | **43** | **43 ✅** |

---

## 二、与下一份任务的联系

### 对接方：组员B（Module B）

- **C → B 的数据流**：C 模块的 `subscriptions.preferences` 字段存储用户标签偏好，B 模块在生成简报时可读取此字段做内容匹配
- **接口**：B 模块可通过 `GET /api/user/{openid}/profile` 获取用户画像（标签 + 权重映射）
- **数据表**：`subscriptions` 表的 `preferences` JSONB 字段格式为 `{"tags": ["LLM", "开源", ...]}`

### 对接方：组员D（Module D）

- **C → D 的数据流**：D 模块发布时可调用 `POST /push` 触发个性化推送
- **接口**：`POST /push` 支持 `type` 参数（morning/evening），自动取最新简报并按标签过滤

### 对接方：组长（Module E）

- **E → C 的调度**：E 模块的调度器在早晚报生成后调用 `POST /push` 触发推送
- **数据表**：C 模块读写 `subscriptions`、`user_behavior` 表，E 模块 Dashboard 可读取这些数据做用户行为统计

---

## 三、测试结果

### 测试环境

- Python 3.12.10
- pytest 9.0.3 + pytest-asyncio + pytest-httpx
- 无 PostgreSQL（mock 模式测试）

### 测试详情

#### test_weixin_oa.py（20 项）

- 签名验证：正确签名、错误签名、未配置 token
- XML 解析：文字消息、关注事件、取关事件
- 回复构建：文本回复、图文回复
- 标签解析：空格分隔、中文顿号、无效标签、混合
- 消息处理：关注回复引导、取关返回 None、"订阅"返回标签列表、"偏好"返回 H5 链接、"订阅 LLM 开源 Agent"解析标签、无效标签提示、未知文字引导、图片消息忽略

#### test_tags.py（12 项）

- 标签列表：返回正确结构、包含预期标签
- 用户偏好：设置偏好、获取偏好、未知用户返回空
- 用户画像：返回正确结构、有标签、有点击记录
- 行为上报：click/view/share、无效 action 返回 400

#### test_push_v2.py（11 项）

- 标签过滤：匹配、跨 section、无匹配兜底、冷启动、结构保持
- 个性化推送：batch_push 个性化 + 兜底
- 接口测试：dry_run with type、dry_run with briefing_id、无参数 400、type 不存在 404、返回含个性化字段

---

## 四、文件目录

```
module-c/
├── backend/
│   ├── __init__.py
│   ├── auth.py              (未改)
│   ├── config.py            (修改 — 加公众号配置)
│   ├── db.py                (未改)
│   ├── main.py              (修改 — 注册新路由)
│   ├── mock_data.py         (修改 — 加标签+行为假数据)
│   ├── models.py            (修改 — 加新模型)
│   ├── push.py              (修改 — 个性化推送)
│   ├── tags.py              (新增 — 标签+行为+画像)
│   ├── weixin_oa.py         (新增 — 公众号回调)
│   └── requirements.txt     (未改)
├── h5/
│   └── preferences.html     (新增 — 标签选择页)
├── tests/
│   ├── __init__.py
│   ├── conftest.py          (未改)
│   ├── test_auth.py         (未改)
│   ├── test_main.py         (未改)
│   ├── test_push.py         (未改)
│   ├── test_push_v2.py      (新增 — 个性化推送测试)
│   ├── test_tags.py         (新增 — 标签+行为测试)
│   └── test_weixin_oa.py    (新增 — 公众号回调测试)
├── miniprogram/             (未改)
├── Phase2_组员C_计划书.md
└── Phase2_组员C_对接计划书.md (本文件)
```

---

## 五、注意事项

1. **微信 5 秒超时**：`POST /weixin/callback` 收到消息后立即返回空响应，异步处理（`asyncio.create_task`）
2. **冷启动兜底**：无标签用户推送默认综合简报，不返回空白
3. **Mock 模式**：无 PostgreSQL 时自动使用内置假数据，所有接口可正常运行
4. **H5 页面**：部署在 module-c 内部，通过 nginx 的 `/h5/` 路径暴露
5. **标签体系**：12 个预置标签，与 `schema_v2.sql` 的 `tag_catalog` 表一致
