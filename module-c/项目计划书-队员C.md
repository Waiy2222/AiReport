# 队员 C — 微信小程序模块 · 详细计划书

> 日期：2026-05-24
> 角色：组员 C
> 职责：把 briefings 表里的简报展示在小程序上，支持订阅推送
> 原则：不调别人接口，只读写自己负责的数据库表（briefings 读，subscriptions 读写）

---

## 一、总文件目录

```
module-c/
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口 + 所有路由
│   ├── config.py               # 环境变量与配置项
│   ├── db.py                   # 数据库连接（组长已提供骨架）
│   ├── models.py               # Pydantic 数据模型 + 数据库查询
│   ├── auth.py                 # 微信登录验证
│   ├── push.py                 # 订阅消息批量推送
│   └── requirements.txt        # Python 依赖
├── miniprogram/
│   ├── app.json                # 小程序全局配置
│   ├── app.js                  # 小程序入口逻辑
│   ├── app.wxss                # 全局样式
│   ├── utils/
│   │   ├── api.js              # 后端 API 请求封装
│   │   └── date.js             # 日期格式化工具
│   └── pages/
│       ├── index/
│       │   ├── index.js        # 首页逻辑（早报/晚报切换）
│       │   ├── index.json      # 页面配置
│       │   ├── index.wxml      # 首页结构
│       │   └── index.wxss      # 首页样式
│       ├── detail/
│       │   ├── detail.js       # 单期详情逻辑
│       │   ├── detail.json     # 页面配置
│       │   ├── detail.wxml     # 详情页结构
│       │   └── detail.wxss     # 详情页样式
│       ├── history/
│       │   ├── history.js      # 历史简报列表逻辑
│       │   ├── history.json    # 页面配置
│       │   ├── history.wxml    # 历史页结构
│       │   └── history.wxss    # 历史页样式
│       └── mine/
│           ├── mine.js         # 个人中心/订阅设置逻辑
│           ├── mine.json       # 页面配置
│           ├── mine.wxml       # 我的页结构
│           └── mine.wxss       # 我的页样式
└── tests/
    ├── __init__.py
    ├── test_main.py            # 后端 /health + 所有 GET/POST 接口测试
    ├── test_auth.py            # 微信登录验证测试
    ├── test_push.py            # 订阅推送测试
    └── conftest.py             # pytest fixtures（测试数据库等）
```

---

## 二、逐文件详细计划

---

### 文件 1：`backend/config.py`

**功能函数：**
- 读取环境变量（数据库连接、微信 AppID/AppSecret、模板消息 ID 等）
- 提供 `Settings` 类，集中管理所有配置项

**调试检测点：**
1. `Settings` 类能正确读取 `.env` 中的变量
2. 缺少必填变量时能给出明确错误提示
3. 数据库连接字符串格式正确

**测试方案：**
- 单元测试：mock 环境变量，验证 Settings 各字段读取
- 边界测试：测试缺少变量时的报错行为

**预期测试结果：**
- 所有必填变量正常读取，缺省变量有默认值
- 缺必填变量时抛出清晰异常

---

### 文件 2：`backend/models.py`

**功能函数：**
| 函数 | 用途 |
|------|------|
| `BriefingOut` | Pydantic 模型，定义 API 返回的简报结构 |
| `BriefingListItem` | Pydantic 模型，历史列表项结构 |
| `SubscribeIn` | Pydantic 模型，订阅请求体 |
| `PushResult` | Pydantic 模型，推送结果 |
| `get_latest_briefing(db, type)` | 查最新一期简报 |
| `get_briefing_history(db, page, size, keyword)` | 查历史列表（支持搜索） |
| `get_briefing_by_id(db, id)` | 查单期详情 |
| `upsert_subscription(db, openid, enabled)` | 新增/更新订阅 |
| `get_active_subscribers(db)` | 查所有已订阅用户 |
| `count_briefings(db, type)` | 统计简报数量 |

**调试检测点：**
1. SQL 查询能正确连接 PostgreSQL，取到 seed_data 的假数据
2. `get_latest_briefing` 按 `created_at DESC` 返回最新一条，区分 morning/evening
3. `get_briefing_history` 分页正确，keyword 搜索能匹配 title
4. `upsert_subscription` 幂等：同一 openid 多次调用不报错
5. 数据库断连时能报出明确错误而非死等

**测试方案：**
- 写 4 个 pytest 用例：查最新简报、查历史列表（含分页+搜索）、查单期、订阅 upsert
- 用 seed_data 的假 briefings 做数据源
- 每个用例断言返回结构与 Pydantic 模型一致

**预期测试结果：**
- 4 个用例全部通过
- 分页逻辑：page=1, size=10 返回 10 条以内
- 搜索逻辑：keyword="AI" 匹配含 AI 的标题

---

### 文件 3：`backend/db.py`

**功能函数：**
- `get_db()` — 数据库连接池管理（组长提供骨架，需要验证可用性）

**调试检测点：**
1. `get_db()` 能返回可用连接
2. 连接池在多次调用后不泄漏
3. 连接失败时有清晰异常

**测试方案：**
- 在 `conftest.py` 中用 `get_db()` 创建测试连接，执行 `SELECT 1`

**预期测试结果：**
- `SELECT 1` 返回成功
- 重复调用 `get_db()` 不会报连接池耗尽

---

### 文件 4：`backend/auth.py`

**功能函数：**
| 函数 | 用途 |
|------|------|
| `code_to_openid(js_code)` | 调用微信 `jscode2session` 接口换取 openid |
| `verify_token(authorization)` | 从请求头中提取并验证 token（简化版用 openid） |
| `get_user_openid(request)` | 从请求中解析当前用户 openid |

**调试检测点：**
1. 传入合法 `js_code` 能换到 openid（需微信开发者工具生成的临时 code）
2. 传入非法 code 返回错误码并记录日志
3. `verify_token` 在无 token 时返回 401
4. 微信 API 超时时能返回友好提示

**测试方案：**
- 单元测试：mock `httpx.AsyncClient`，模拟微信 API 返回
- 集成测试：用微信开发者工具获取真实 code，调用接口验证

**预期测试结果：**
- mock 测试：合法 code 返回 openid，非法 code 返回 None
- 集成测试：真实 code 成功换取 openid

---

### 文件 5：`backend/push.py`

**功能函数：**
| 函数 | 用途 |
|------|------|
| `get_access_token(appid, secret)` | 获取微信小程序 access_token |
| `send_subscribe_message(openid, briefing, access_token)` | 发送单条订阅消息 |
| `batch_push(briefing_id)` | 批量推送给所有已订阅用户 |
| `push_route(db, briefing_id)` | `/push` 接口的处理函数 |

**调试检测点：**
1. `get_access_token` 能正常获取并缓存 token（2 小时内复用）
2. `send_subscribe_message` 发送模板消息，手机能收到
3. `batch_push` 批量发送，单用户失败不影响其他用户
4. 推送结果记录 subscriptions 表中的推送时间
5. token 过期后自动刷新

**测试方案：**
- 单元测试：mock 微信 API，验证 access_token 缓存逻辑
- 单元测试：mock 微信 API，验证单条发送和批量发送的成功/失败计数
- 集成测试：用真实 AppID，推给一个测试 openid，手机验证

**预期测试结果：**
- mock 测试：100 个订阅用户，1 个失败 → 返回 `{total: 100, success: 99, failed: 1}`
- 集成测试：手机收到订阅消息，点击跳转到对应简报详情页

---

### 文件 6：`backend/main.py`

**功能函数：**
| 路由 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/briefings/latest` | GET | 取最新简报（query: type=morning/evening） |
| `/api/briefings/history` | GET | 历史列表（query: page, size, keyword） |
| `/api/briefings/{id}` | GET | 单期详情 |
| `/api/subscribe` | POST | 用户订阅（body: js_code） |
| `/api/unsubscribe` | POST | 取消订阅（body: openid） |
| `/push` | POST | 批量推送订阅消息（body: briefing_id） |

**调试检测点：**
1. `/health` 返回 `{"status": "ok"}`，响应时间 < 50ms
2. `/api/briefings/latest?type=morning` 返回 seed_data 中的假早报
3. `/api/briefings/latest?type=evening` 返回 seed_data 中的假晚报
4. `/api/briefings/history?page=1&size=10` 返回分页列表
5. `/api/briefings/history?keyword=AI` 返回匹配结果
6. `/api/briefings/{id}` 传入存在/不存在的 ID 分别处理
7. `/api/subscribe` 传入合法 js_code 创建订阅
8. `/api/unsubscribe` 传入 openid 取消订阅
9. `/push` 传入 briefing_id 触发批量推送
10. 请求格式错误时返回 422（Pydantic 自动校验）

**测试方案：**
- 使用 pytest + httpx TestClient 覆盖所有路由
- 每个路由写正例 + 负例（缺参数、错误参数、资源不存在的 404）
- 在 conftest.py 中初始化测试数据库

**预期测试结果：**
- 所有 7 个路由正例通过
- 负例返回 4xx，不返回 500
- `/health` 200 OK

---

### 文件 7：`tests/conftest.py`

**功能函数：**
- `test_db` fixture — 创建测试用 PostgreSQL 连接
- `client` fixture — 创建 FastAPI TestClient
- `seed_test_data` fixture — 向测试库插入最小假数据集

**调试检测点：**
1. fixture 正确创建、正确拆毁
2. 测试数据库不受正式库数据污染

**测试方案：**
- 运行 pytest 确认 fixture 可用

**预期测试结果：**
- pytest 收集到所有用例，fixture 注入成功

---

### 文件 8：`tests/test_main.py`

**功能函数：**
- `test_health(client)` — GET /health
- `test_latest_briefing_morning(client)` — GET /api/briefings/latest?type=morning
- `test_latest_briefing_evening(client)` — GET /api/briefings/latest?type=evening
- `test_latest_briefing_missing_type(client)` — 缺 type 参数返回错误
- `test_history_default(client)` — GET /api/briefings/history 默认分页
- `test_history_with_keyword(client)` — keyword=AI 搜索
- `test_briefing_detail_found(client)` — 存在的 ID 返回详情
- `test_briefing_detail_not_found(client)` — 不存在的 ID 返回 404
- `test_subscribe(client)` — POST /api/subscribe
- `test_unsubscribe(client)` — POST /api/unsubscribe
- `test_push(client)` — POST /push

**调试检测点：**
- 见 main.py 的 10 个检测点

**测试方案：**
- 每个函数对应一个检测点，用 pytest 断言

**预期测试结果：**
- 11 个用例全部通过

---

### 文件 9：`tests/test_auth.py`

**功能函数：**
- `test_code_to_openid_valid()` — mock 微信返回合法 openid
- `test_code_to_openid_invalid()` — mock 微信返回错误码
- `test_verify_token_missing()` — 无 token 返回 401
- `test_verify_token_invalid()` — token 无效返回 401

**调试检测点：**
- 见 auth.py 的 4 个检测点

**测试方案：**
- 4 个 pytest 用例，用 `unittest.mock` 模拟 httpx 请求

**预期测试结果：**
- 4 个用例全部通过

---

### 文件 10：`tests/test_push.py`

**功能函数：**
- `test_get_access_token_cached()` — token 2 小时内复用
- `test_send_single_message()` — 单条发送成功
- `test_batch_push_partial_failure()` — 100 个用户中 1 个失败
- `test_batch_push_all_success()` — 全部成功

**调试检测点：**
- 见 push.py 的 5 个检测点

**测试方案：**
- 4 个 pytest 用例，mock 微信 API

**预期测试结果：**
- 4 个用例通过

---

### 文件 11：`miniprogram/app.json`

**功能：**
- 小程序全局配置：pages 注册、window 样式、tabBar 配置

**调试检测点：**
1. 4 个页面全部注册：index, detail, history, mine
2. tabBar 显示首页和历史两个 tab
3. 微信开发者工具中编译不报错

**测试方案：**
- 微信开发者工具打开项目 → 编译 → 检查控制台无报错

**预期测试结果：**
- 编译通过，底部 tabBar 显示正常

---

### 文件 12：`miniprogram/app.js`

**功能函数：**
| 函数/变量 | 用途 |
|-----------|------|
| `globalData` | 全局共享数据（当前用户 openid、当前简报等） |
| `App.onLaunch()` | 小程序启动时调用 wx.login 获取 code 并换取 openid |
| `checkUpdate()` | 检查小程序版本更新 |

**调试检测点：**
1. 启动后 `globalData.openid` 被正确赋值
2. 登录失败时不影响页面渲染（可查看无订阅模式）

**测试方案：**
- 微信开发者工具启动 + 真机调试

**预期测试结果：**
- 控制台打印 openid，App 正常启动

---

### 文件 13：`miniprogram/utils/api.js`

**功能函数：**
| 函数 | 用途 |
|------|------|
| `request(url, method, data)` | 封装 `wx.request`，自动拼接 baseUrl |
| `getLatestBriefing(type)` | GET /api/briefings/latest?type= |
| `getBriefingHistory(page, size, keyword)` | GET /api/briefings/history |
| `getBriefingDetail(id)` | GET /api/briefings/{id} |
| `subscribe(jsCode)` | POST /api/subscribe |
| `unsubscribe(openid)` | POST /api/unsubscribe |

**调试检测点：**
1. `request` 能正确处理 200 和 4xx 响应
2. 网络错误时返回统一格式 `{error: true, message: ...}`
3. 每个函数调用正确的 URL 和方法

**测试方案：**
- 对比 seed_data 中的假简报，调用 API 验证返回数据
- 微信开发者工具 Network 面板抓包确认

**预期测试结果：**
- 6 个函数全部能正常调用后端接口

---

### 文件 14：`miniprogram/pages/index/index.*`

**功能：**
- 首页：顶部早报/晚报 Tab 切换
- TL;DR 卡片列表（10-15 条一句话要点）
- 下拉刷新

**核心数据流：**
```
onLoad → getLatestBriefing('morning') → setData({briefing}) → 渲染
onTabSwitch → getLatestBriefing(type) → setData → 重新渲染
```

**调试检测点：**
1. 默认显示早报 Tab，卡片列表正确渲染
2. 切换到晚报 Tab 后数据刷新
3. 空状态处理：无简报时显示"暂无简报"占位
4. 网络错误时显示"加载失败" + 重试按钮
5. 下拉刷新能重新拉取数据

**测试方案：**
- 微信开发者工具：用 seed_data 验证渲染效果
- 真机预览：检查下拉刷新、Tab 切换流畅度

**预期测试结果：**
- 首页正常展示假简报的 TL;DR 卡片
- 早报/晚报切换正常，数据对应切换

---

### 文件 15：`miniprogram/pages/detail/detail.*`

**功能：**
- 展示单期简报全部内容：
  - 标题 + 日期 + 类型（早报/晚报）
  - TL;DR 列表
  - sections 分类折叠（研究进展/开源工具/行业动态）
  - key_takeaways 关键趋势
  - 每条资讯的原文链接（可复制或跳转）

**核心数据流：**
```
onLoad(id) → getBriefingDetail(id) → setData → 渲染各 section
```

**调试检测点：**
1. 从首页点击卡片跳转详情，数据正确渲染
2. section 折叠/展开交互正常
3. 原文链接可点击跳转（使用 `<web-view>` 或 `wx.setClipboardData`）
4. 空 section 不显示空白区域
5. 传入不存在的 ID 显示"简报不存在"

**测试方案：**
- 微信开发者工具：传入 seed_data 中的假简报 ID 查看渲染
- 点击原文链接验证跳转

**预期测试结果：**
- 详情页正确展示简报所有字段
- 折叠交互流畅，链接可跳转

---

### 文件 16：`miniprogram/pages/history/history.*`

**功能：**
- 按日期列表展示历史简报
- 顶部搜索框，输入 keyword 筛选
- 上拉加载更多（分页）

**核心数据流：**
```
onLoad → getBriefingHistory(1, 20) → setData({list}) → 渲染
onSearch → getBriefingHistory(1, 20, keyword) → 过滤
onReachBottom → getBriefingHistory(nextPage, 20) → 追加
```

**调试检测点：**
1. 历史列表按日期倒序排列
2. 搜索框输入关键词能筛选
3. 滚动到底部自动加载下一页
4. 没有更多数据时显示"已加载全部"
5. 搜索无结果时显示"未找到相关简报"

**测试方案：**
- 微信开发者工具：用 seed_data 中的 3 期假简报验证分页和搜索
- 真机：测试上拉加载更多的手势

**预期测试结果：**
- 3 期假简报全部显示，按日期倒序
- 搜索功能正确过滤

---

### 文件 17：`miniprogram/pages/mine/mine.*`

**功能：**
- 显示当前用户 openid（脱敏）
- 每日早报/晚报推送订阅开关
- 关于页面入口（项目简介）

**核心数据流：**
```
onLoad → 读取 app.globalData.openid → getSubscriptions() → setData({morningOn, eveningOn})
onToggleMorning → subscribe/unsubscribe API → 更新开关状态
```

**调试检测点：**
1. 订阅开关默认关闭
2. 打开开关时调 `subscribe` 接口，数据库有记录
3. 关闭开关时调 `unsubscribe` 接口，数据库对应记录更新
4. 未登录时不能操作订阅开关
5. 微信订阅消息授权弹窗正常弹出

**测试方案：**
- 微信开发者工具：操作订阅开关，同时 curl 查 subscriptions 表确认
- 真机：查看微信订阅消息授权弹窗

**预期测试结果：**
- 开关操作与数据库状态一致
- 授权弹窗正常

---

### 文件 18：`backend/requirements.txt`

**内容：**
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
asyncpg==0.30.0
httpx==0.28.1
python-dotenv==1.0.1
pydantic==2.10.4
pytest==8.3.5
pytest-asyncio==0.25.2
```

---

## 三、测试日志模板

> 以下日志按时间流记录，从第一份测试开始，每次测试叠加之前的所有测试操作，确保连通性无回归。

| 时间 | 序号 | 测试文件 | 测试数据 | 测试内容 | 预期结果 | 实际结果 | 通过/失败 | 原因分析 |
|------|------|----------|----------|----------|----------|----------|-----------|----------|
| | 1 | config.py | .env 配置 | 读取所有环境变量 | Settings 字段正确 | | | |
| | 2 | config.py | 删除必填变量 | 验证报错 | 抛出清晰异常 | | | |
| | 3 | db.py + conftest.py | 连接 PostgreSQL | SELECT 1 | 返回成功 | | | |
| | 4 | models.py | seed_data 假简报 | get_latest_briefing(morning) | 返回假早报 | | | |
| | 5 | models.py | seed_data 假简报 | get_briefing_history(1,10) | 分页结果 ≤10 条 | | | |
| | 6 | models.py | seed_data 假简报 | get_briefing_history(1,10,'AI') | 匹配含 AI 的标题 | | | |
| | 7 | models.py | seed_data 假简报 | get_briefing_by_id(存在ID) | 返回完整简报 | | | |
| | 8 | models.py | seed_data 假简报 | get_briefing_by_id(不存在ID) | 返回 None | | | |
| | 9 | models.py | 新 openid | upsert_subscription(openid, true) | 插入成功，再次调用幂等 | | | |
| | 10 | models.py | 已有 openid | get_active_subscribers() | 返回包含刚订阅的 openid | | | |
| | 11 | auth.py | mock js_code='test' | code_to_openid('test') | 返回 mock openid | | | |
| | 12 | auth.py | mock js_code='bad' | code_to_openid('bad') | 返回 None | | | |
| | 13 | auth.py | 无 Authorization 头 | verify_token(None) | 401 | | | |
| | 14 | push.py | mock 微信 API | get_access_token() | 返回 mock token | | | |
| | 15 | push.py | mock 微信 API | send_subscribe_message() | 返回成功 | | | |
| | 16 | push.py | mock 100 用户 1 失败 | batch_push() | {total:100, success:99, failed:1} | | | |
| | 17 | push.py | mock 100 用户全成功 | batch_push() | {total:100, success:100, failed:0} | | | |
| | 18 | main.py | httpx TestClient | GET /health | 200, {"status":"ok"} | | | |
| | 19 | main.py | httpx TestClient | GET /api/briefings/latest?type=morning | 200, 返回简报 JSON | | | |
| | 20 | main.py | httpx TestClient | GET /api/briefings/latest (缺 type) | 422/400 | | | |
| | 21 | main.py | httpx TestClient | GET /api/briefings/history?page=1&size=10 | 200, 列表 | | | |
| | 22 | main.py | httpx TestClient | GET /api/briefings/history?keyword=AI | 200, 过滤结果 | | | |
| | 23 | main.py | httpx TestClient | GET /api/briefings/{存在ID} | 200, 完整简报 | | | |
| | 24 | main.py | httpx TestClient | GET /api/briefings/{不存在ID} | 404 | | | |
| | 25 | main.py | httpx TestClient | POST /api/subscribe (合法code) | 201 | | | |
| | 26 | main.py | httpx TestClient | POST /api/unsubscribe (已有openid) | 200 | | | |
| | 27 | main.py | httpx TestClient | POST /push (有效briefing_id) | 200, 含推送统计 | | | |
| | 28 | main.py | httpx TestClient | POST /push (无效briefing_id) | 404 | | | |
| | 29 | 连通性 | 全部已有接口 | 重跑全部 28 个测试 | 全部通过 | | | |
| | 30 | miniprogram | 微信开发者工具 | 编译 app.json | 无报错 | | | |
| | 31 | miniprogram | 微信开发者工具 | app.js onLaunch → wx.login | openid 赋值 | | | |
| | 32 | miniprogram | 微信开发者工具 | api.js getLatestBriefing('morning') | 返回假早报数据 | | | |
| | 33 | miniprogram | 微信开发者工具 | 首页渲染早报 TL;DR 卡片 | 卡片列表正确 | | | |
| | 34 | miniprogram | 微信开发者工具 | 切换到晚报 Tab | 晚报卡片渲染 | | | |
| | 35 | miniprogram | 微信开发者工具 | 点击卡片跳转详情页 | 详情页渲染完整简报 | | | |
| | 36 | miniprogram | 微信开发者工具 | 详情页 section 折叠/展开 | 交互正常 | | | |
| | 37 | miniprogram | 微信开发者工具 | 点击原文链接 | 跳转/复制成功 | | | |
| | 38 | miniprogram | 微信开发者工具 | 历史页 → 搜索 "AI" | 过滤结果 | | | |
| | 39 | miniprogram | 微信开发者工具 | 历史页 → 上拉加载更多 | 追加下一页 | | | |
| | 40 | miniprogram | 微信开发者工具 | 我的页 → 打开订阅开关 | subscribe 接口调用成功 | | | |
| | 41 | miniprogram | 微信开发者工具 | 我的页 → 关闭订阅开关 | unsubscribe 接口调用成功 | | | |
| | 42 | 连通性 | 全部已有测试 | 重新跑 1-41 全部测试 | 全部通过 | | | |

---

## 四、参考资源

| 参考项 | 路径/来源 |
|--------|-----------|
| 数据库表结构 | `contracts/schema.sql` |
| 假数据 | `contracts/seed_data.sql` |
| 接口规范 | `contracts/api-spec.yaml` |
| 组长 FastAPI 骨架 | `module-c/backend/main.py`（组长已建） |
| 微信小程序文档 | developers.weixin.qq.com/miniprogram/dev/ |

---

## 五、开发顺序（推荐）

```
第一步：backend/config.py + db.py + models.py        (后端基础，1 天)
第二步：backend/main.py + tests/                      (后端接口 + 测试，1 天)
第三步：backend/auth.py + push.py + tests/            (登录 + 推送，1 天)
第四步：miniprogram/app.* + utils/                    (小程序骨架，0.5 天)
第五步：miniprogram pages/index + detail              (核心页面，1.5 天)
第六步：miniprogram pages/history + mine              (辅助页面，1 天)
第七步：真机调试 + 订阅消息集成                        (收尾，0.5 天)
```
