# Phase 2 组员C — 微信公众号 + 用户偏好系统 · 详细计划书

> 日期：2026-05-28
> 基于：Phase 2 计划书 + contracts/schema_v2.sql + shared/rag.py + 现有 module-c 代码

---

## 总体目标

在 Phase 1 的小程序后端基础上，新增：
1. 微信公众号消息回调接入（C1）
2. 标签体系 + 用户偏好 CRUD（C2）
3. 用户行为追踪（C3）
4. 个性化推送 — 按标签匹配内容（C4）
5. H5 标签选择页（C5）

---

## 文件清单（共 8 个文件，含 3 个测试文件）

### 1. config.py（修改）
- **功能**：新增微信公众号配置项
- **新增变量**：
  - `WX_OA_TOKEN` — 公众号服务器配置 Token
  - `WX_OA_APPID` — 公众号 AppID
  - `WX_OA_SECRET` — 公众号 AppSecret
  - `WX_OA_ENCODING_AES_KEY` — 消息加解密密钥（可选）
- **调试检测点**：Settings 实例化后各字段类型正确
- **测试方案**：import 检查，确认新字段存在且默认为空字符串
- **预期结果**：`settings.WX_OA_TOKEN` 默认为 `""`

### 2. models.py（修改）
- **功能**：新增 Phase 2 数据模型
- **新增模型**：
  - `PreferencesRequest(openid, tags: list[str])` — 设置偏好
  - `BehaviorRequest(openid, briefing_id, action, item_index?, item_title?, item_url?, item_tags?)` — 行为上报
  - `WeixinCallbackParams(signature, timestamp, nonce, echostr)` — 微信验证参数
  - `TagItem(tag, label_zh, description)` — 标签项
  - `UserProfile(openid, tags, recent_clicks, weight_map)` — 用户画像
- **调试检测点**：各模型字段验证（必填/可选/类型）
- **测试方案**：单元测试验证模型实例化和验证
- **预期结果**：缺少必填字段时抛 ValidationError

### 3. weixin_oa.py（新增）
- **功能**：微信公众号消息回调处理
- **核心函数**：
  - `verify_signature(signature, timestamp, nonce) → bool` — SHA1 签名验证
  - `parse_xml_message(xml_bytes) → dict` — 解析微信 XML 消息
  - `build_text_reply(from_user, to_user, content) → str` — 构建文本回复 XML
  - `build_news_reply(from_user, to_user, articles) → str` — 构建图文回复 XML
  - `handle_message(msg_dict) → str | None` — 消息路由处理（关注/取关/文字）
- **消息处理逻辑**：
  - 关注事件 → 自动回复引导文字
  - 回复 `订阅` → 返回标签列表
  - 回复 `订阅 LLM 开源 Agent` → 解析标签写入 subscriptions
  - 回复 `偏好` → 返回 H5 链接
  - 取关事件 → 更新 subscriptions.subscribed=false
- **调试检测点**：签名验证正确性、XML 解析完整性、消息路由准确性
- **测试方案**：mock 微信消息 XML，验证各场景回复内容
- **预期结果**：关注回复引导文字、"订阅"回复标签列表、"偏好"回复链接

### 4. tags.py（新增）
- **功能**：标签 CRUD + 用户行为追踪 + 用户画像
- **路由（在 main.py 中注册）**：
  - `GET /api/tags` — 返回可用标签列表（从 tag_catalog 表读取，fallback 到硬编码列表）
  - `POST /api/user/preferences` — 设置用户偏好标签（写入 subscriptions.preferences）
  - `GET /api/user/preferences?openid=xxx` — 获取用户偏好
  - `GET /api/user/{openid}/profile` — 用户画像（标签 + 近期点击摘要 + 权重映射）
  - `POST /api/behavior` — 上报用户行为（写入 user_behavior 表）
- **调试检测点**：DB 读写正确性、mock data fallback、JSONB 字段序列化
- **测试方案**：mock DB 和 mock data 两种模式测试
- **预期结果**：无 DB 时返回 mock 标签列表，有 DB 时读写正确

### 5. push.py（修改）
- **功能**：按用户标签个性化推送
- **修改 `batch_push`**：
  - 新增参数 `briefing_sections` — 完整简报内容（含 sections 和 tags）
  - 对每个用户：根据 `preferences.tags` 过滤/排序 sections 中的 items
  - 有标签用户 → 只推匹配标签的内容
  - 无标签用户 → 推默认综合简报（冷启动兜底）
- **新增函数**：
  - `filter_briefing_by_tags(briefing, user_tags) → dict` — 按标签过滤简报内容
- **调试检测点**：标签匹配逻辑、冷启动兜底、过滤后内容完整性
- **测试方案**：给定简报 + 不同标签用户，验证过滤结果
- **预期结果**：有标签用户只收到匹配内容，无标签用户收到全部

### 6. main.py（修改）
- **功能**：注册所有新路由
- **新增路由**：
  - `GET/POST /weixin/callback` — 公众号回调（GET 验证，POST 消息）
  - `GET /api/tags` — 标签列表
  - `GET/POST /api/user/preferences` — 用户偏好
  - `GET /api/user/{openid}/profile` — 用户画像
  - `POST /api/behavior` — 行为上报
  - `POST /push` — 更新：支持 type 参数，按标签个性化
- **调试检测点**：路由注册正确、请求参数验证、异步处理
- **测试方案**：httpx AsyncClient 测试所有路由
- **预期结果**：所有路由返回正确状态码和数据

### 7. h5/preferences.html（新增）
- **功能**：极简标签选择 H5 页面
- **特性**：
  - 从 `/api/tags` 加载可用标签
  - 复选框形式展示标签（chip 样式）
  - 从 URL 参数获取 openid
  - 提交时调用 `POST /api/user/preferences`
  - 移动端适配（viewport meta）
  - 微信内置浏览器兼容
- **调试检测点**：API 调用正确性、标签选中状态、提交成功反馈
- **测试方案**：浏览器手动打开验证
- **预期结果**：页面展示标签列表，选中后提交成功

### 8. mock_data.py（修改）
- **功能**：新增标签和行为假数据
- **新增数据**：
  - `TAG_CATALOG` — 12 个预置标签（与 schema_v2.sql 一致）
  - `MOCK_BEHAVIORS` — 模拟用户点击行为
  - `MOCK_USER_PREFERENCES` — 模拟用户偏好
- **新增函数**：
  - `get_tags()` → 标签列表
  - `get_user_preferences(openid)` → 用户偏好
  - `get_user_behaviors(openid)` → 用户行为
- **调试检测点**：数据结构与 schema_v2.sql 一致
- **测试方案**：函数调用返回正确结构
- **预期结果**：返回与数据库 schema 一致的 mock 数据

---

## 测试文件

### 9. tests/test_weixin_oa.py（新增）
- 测试签名验证（正确/错误）
- 测试 XML 消息解析（关注/文字/取关）
- 测试消息路由回复

### 10. tests/test_tags.py（新增）
- 测试 GET /api/tags
- 测试 POST /api/user/preferences
- 测试 GET /api/user/{openid}/profile
- 测试 POST /api/behavior

### 11. tests/test_push_v2.py（新增）
- 测试按标签过滤简报
- 测试冷启动兜底
- 测试个性化推送流程

---

## 总文件目录

```
module-c/
├── backend/
│   ├── __init__.py          (不改)
│   ├── config.py            (修改 — 加公众号配置)
│   ├── db.py                (不改)
│   ├── models.py            (修改 — 加新模型)
│   ├── weixin_oa.py         (新增 — 公众号回调)
│   ├── tags.py              (新增 — 标签+行为+画像)
│   ├── push.py              (修改 — 个性化推送)
│   ├── main.py              (修改 — 注册新路由)
│   ├── mock_data.py         (修改 — 加假数据)
│   ├── auth.py              (不改)
│   └── requirements.txt     (修改 — 加 hashlib 已内置)
├── h5/
│   └── preferences.html     (新增 — 标签选择页)
├── tests/
│   ├── __init__.py          (不改)
│   ├── conftest.py          (不改)
│   ├── test_main.py         (不改)
│   ├── test_push.py         (不改)
│   ├── test_auth.py         (不改)
│   ├── test_weixin_oa.py    (新增)
│   ├── test_tags.py         (新增)
│   └── test_push_v2.py      (新增)
└── Phase2_组员C_计划书.md    (本文件)
```

---

## 执行顺序

1. config.py（修改）— 基础配置
2. models.py（修改）— 数据模型
3. mock_data.py（修改）— 假数据
4. weixin_oa.py（新增）— 公众号回调
5. tags.py（新增）— 标签+行为 API
6. push.py（修改）— 个性化推送
7. main.py（修改）— 注册路由
8. h5/preferences.html（新增）— H5 页面
9. tests/test_weixin_oa.py（新增）— 测试
10. tests/test_tags.py（新增）— 测试
11. tests/test_push_v2.py（新增）— 测试

每步完成后运行测试验证，通过后再进行下一步。
