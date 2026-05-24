-- ============================================================
-- AI 资讯早报/晚报智能体 · 种子数据
-- 让每个模块拿到即可独立开发，不需要等其他模块完成
-- ============================================================

-- ── raw_items: 30条假 AI 资讯（模拟 A 模块抓取结果，供 B 开发用）────
INSERT INTO raw_items (id, source, title, url, content, author, published_at, batch_id) VALUES
('a0000001-0000-0000-0000-000000000001', 'github', 'LangChain发布v0.3版本，新增多Agent协作能力', 'https://github.com/langchain-ai/langchain/releases/tag/v0.3.0', 'LangChain v0.3.0 正式发布，新增MultiAgentCoordinator类，支持多个Agent之间的消息传递和任务分配。', 'langchain-ai', '2026-05-24 02:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000002', 'github', 'Open Source LLM Tool Calling Framework: Gorilla v2.0', 'https://github.com/ShishirPatil/gorilla', 'Gorilla v2.0 发布，新增对Claude、Gemini、DeepSeek等模型的tool calling支持，准确率提升至95%。', 'ShishirPatil', '2026-05-24 04:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000003', 'github', 'Ollama Stars突破10万，成为最流行的本地LLM运行时', 'https://github.com/ollama/ollama', 'Ollama在GitHub上Stars突破10万，支持macOS/Linux/Windows三平台，最新版本新增对DeepSeek-V4的本地运行支持。', 'ollama', '2026-05-23 18:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000004', 'github', 'AutoGPT发布自主Agent框架v0.6', 'https://github.com/Significant-Gravitas/AutoGPT', 'AutoGPT v0.6 重构了核心调度引擎，支持子Agent的动态创建和销毁，内存管理优化30%。', 'Significant-Gravitas', '2026-05-24 01:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000005', 'github', 'vLLM发布v0.7.0，推理吞吐量提升2倍', 'https://github.com/vllm-project/vllm/releases/tag/v0.7.0', 'vLLM v0.7.0引入PagedAttention V3和FP8量化，单卡A100可跑70B模型，吞吐量相较v0.6提升2倍。', 'vllm-project', '2026-05-24 06:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000006', 'github', 'MCP (Model Context Protocol) Python SDK正式发布', 'https://github.com/modelcontextprotocol/python-sdk', 'Anthropic开源MCP的Python SDK，提供标准化的AI模型上下文管理接口，支持多Provider切换。', 'modelcontextprotocol', '2026-05-23 14:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000007', 'github', 'ChromaDB发布向量数据库v1.0', 'https://github.com/chroma-core/chroma', 'ChromaDB v1.0正式版发布，支持十亿级向量检索，新增HNSW索引，查询延迟降至5ms。', 'chroma-core', '2026-05-24 00:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000008', 'github', 'HuggingFace Transformers v5.0架构重构', 'https://github.com/huggingface/transformers', 'Transformers v5.0发布，统一了LLM、多模态和扩散模型的API，引入AutoModelV2自动选型机制。', 'huggingface', '2026-05-23 22:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000009', 'github', 'Meta开源Llama-4-R1推理增强模型', 'https://github.com/meta-llama/llama4', 'Meta发布Llama-4-R1，基于强化学习的推理增强版本，在MATH和ARC测试中达到GPT-5同级水平，采用MIT许可证。', 'meta-llama', '2026-05-24 03:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000010', 'github', 'Dify发布AI应用构建平台v1.5', 'https://github.com/langgenius/dify', 'Dify v1.5新增多Agent工作流、RAG管道可视化编排、知识库多格式支持（PDF/Word/Notion/网页）', 'langgenius', '2026-05-23 20:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000011', 'hackernews', 'DeepSeek-V4:中国首个全开源MoE大模型的技术报告解读', 'https://news.ycombinator.com/item?id=40000001', 'DeepSeek发布V4技术报告，MoE架构370B参数，训练成本仅$5M，多项基准超过GPT-4o。HN社区热烈讨论开源vs闭源的未来。', 'tech_review', '2026-05-24 05:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000012', 'hackernews', 'Anthropic发布Claude Opus 4.7，编程能力大幅提升', 'https://news.ycombinator.com/item?id=40000002', 'Claude Opus 4.7在SWE-Bench Verified上达到85%准确率，超越所有竞品。支持200K上下文窗口。', 'ai_explorer', '2026-05-24 07:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000013', 'hackernews', '为什么我们决定将所有微服务迁移到单体应用', 'https://news.ycombinator.com/item?id=40000003', '一位CTO分享将AI创业公司的微服务架构迁移到单体的经验，引发了关于过早优化与工程复杂度的讨论。', 'cto_startup', '2026-05-23 16:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000014', 'hackernews', 'OpenAI被曝正在开发全新推理架构"Strawberry"', 'https://news.ycombinator.com/item?id=40000004', '据The Information报道，OpenAI内部正在开发代号Strawberry的新型推理架构，可能在数学和编程方面有质的飞跃。', 'insider_news', '2026-05-24 08:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000015', 'hackernews', 'Show HN:我做了个开源AI代码审查工具，用本地LLM保护隐私', 'https://news.ycombinator.com/item?id=40000005', '作者分享基于Ollama+Llama-4的开源代码审查工具，完全本地运行，支持GitHub/GitLab集成，已有500+Stars。', 'indie_dev', '2026-05-23 21:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000016', 'rss', 'Google DeepMind发布Gemini 3.0，首次支持Agent原生能力', 'https://blog.google/technology/ai/gemini-3-agent/', 'Gemini 3.0引入Agent API，支持多步工具调用、浏览器自动化和代码执行。在MMLU-Pro上达到92%。', 'Google AI Blog', '2026-05-24 00:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000017', 'rss', '中国信通院发布《2026年AI Agent产业白皮书》', 'https://www.caict.ac.cn/ai-agent-2026', '白皮书指出2026年全球Agent市场规模突破200亿美元，中国企业级Agent应用增长最快，智能客服和代码助手是两大突破口。', '中国信通院', '2026-05-24 06:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000018', 'rss', 'MIT研究团队提出新的Agent评估框架AgentBench V2', 'https://news.mit.edu/2026/agent-bench-v2', 'MIT CSAIL发布AgentBench V2，覆盖200+真实任务场景，包括代码、网络、文件操作等，成为Agent能力评估新标准。', 'MIT News', '2026-05-23 15:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000019', 'rss', 'OpenAI开源GPT-OSS：一个可在消费级硬件上运行的推理模型', 'https://openai.com/blog/gpt-oss', 'OpenAI意外开源GPT-OSS，7B参数，可在MacBook上运行，在数学和代码方面接近GPT-5-mini水平。社区反应两极化。', 'OpenAI Blog', '2026-05-24 04:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000020', 'rss', 'Next.js 16发布：AI-first框架，内置RAG API', 'https://nextjs.org/blog/next-16', 'Vercel发布Next.js 16，首次内置RAG API和AI Agent路由，支持Streaming SSR与Edge Runtime的深度融合。', 'Vercel Blog', '2026-05-23 19:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000021', 'github', 'CrewAI多Agent框架发布v1.0正式版', 'https://github.com/crewAIInc/crewAI', 'CrewAI v1.0发布，新增层级式Agent组织、条件任务流和Human-in-the-Loop审批节点，企业级特性完善。', 'crewAIInc', '2026-05-24 05:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000022', 'hackernews', '微软开源PromptFlow：LLM应用的可视化开发工具', 'https://news.ycombinator.com/item?id=40000006', '微软将内部PromptFlow工具开源，支持可视化编排LLM链、评估和部署。社区对比LangChain和Dify的方案优劣。', 'ms_dev', '2026-05-23 23:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000023', 'rss', '斯坦福发布AI指数2026年度报告', 'https://aiindex.stanford.edu/report/2026/', '斯坦福HAI发布2026年AI指数报告：中国在AI论文数量和专利方面领先，美国在模型能力和投资方面领先。开源模型与闭源模型差距缩小至0.3%。', 'Stanford HAI', '2026-05-24 01:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000024', 'github', 'RAGFlow开源RAG引擎发布v2.0', 'https://github.com/infiniflow/ragflow', 'RAGFlow v2.0新增Graph RAG、多模态检索和Agentic RAG能力，支持非结构化文档深度理解，企业级部署方案完善。', 'infiniflow', '2026-05-23 17:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000025', 'hackernews', 'AI编程助手市场格局分析与2026趋势预测', 'https://news.ycombinator.com/item?id=40000007', '一位资深开发者对GitHub Copilot、Cursor、Claude Code、Windsurf等7款AI编程工具进行深度横评，引发社区对IDE未来的讨论。', 'dev_analyst', '2026-05-24 06:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000026', 'rss', '阿里通义千问发布Qwen-3-Max，中文能力全面领先', 'https://tongyi.aliyun.com/blog/qwen-3-max', '通义千问Qwen-3-Max发布，在C-Eval、CMMLU等中文基准测试中全面领先，支持100万字长上下文，API价格仅为GPT-5的1/10。', '阿里云', '2026-05-24 02:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000027', 'github', 'Langfuse发布LLM可观测性平台v3.0', 'https://github.com/langfuse/langfuse', 'Langfuse v3.0支持实时Token成本追踪、Agent调用链可视化、自动化评估和告警，支持自部署和云服务两种模式。', 'langfuse', '2026-05-23 13:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000028', 'hackernews', 'YC 2026夏季批次：AI初创公司占比首次超过80%', 'https://news.ycombinator.com/item?id=40000008', 'Y Combinator 2026年夏季批次共有230家初创公司，其中AI相关占82%。主要是AI Agent工具、垂直行业AI应用和AI基础设施。', 'yc_observer', '2026-05-24 07:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000029', 'rss', '欧盟AI法案第二阶段正式实施：高风险AI系统需强制备案', 'https://techcrunch.com/2026/05/24/eu-ai-act-phase-2', '欧盟AI法案第二阶段生效，覆盖Agent系统、自动驾驶和医疗AI。要求透明性报告、人工监督机制和风险评估。违规最高罚全球营收的7%。', 'TechCrunch', '2026-05-24 08:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000030', 'github', 'PaddlePaddle发布飞桨3.0：中文AI开发者的首选框架', 'https://github.com/PaddlePaddle/Paddle', '百度飞桨3.0发布，全面支持大模型训练和推理，新增AutoParallel分布式训练，中文NLP预训练模型库扩充至500+。', 'PaddlePaddle', '2026-05-24 00:00:00+00', 'seed-batch-001');

-- ── briefings: 3 期假简报（模拟 B 模块输出，供 C/D 开发用）─────────
INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats) VALUES
('b0000001-0000-0000-0000-000000000001', 'morning', '2026-05-24', 'zh',
  '["DeepSeek-V4技术报告引发全球关注，MoE架构370B参数开源，训练成本仅500万美元",
    "Meta开源Llama-4-R1推理增强模型，MIT许可证，多项基准达GPT-5同级",
    "Anthropic发布Claude Opus 4.7，SWE-Bench Verified准确率85%",
    "OpenAI意外开源GPT-OSS 7B推理模型，可在消费级硬件运行",
    "Google DeepMind发布Gemini 3.0，首次原生支持Agent API",
    "欧盟AI法案第二阶段生效，高风险AI系统需强制备案",
    "YC 2026夏季批次AI初创占比82%，Agent工具和垂直应用成热点",
    "vLLM v0.7推理吞吐量提升2倍，FP8量化支持70B模型单卡部署",
    "CrewAI v1.0和AutoGPT v0.6同日发布，多Agent框架竞争白热化",
    "HuggingFace Transformers v5.0统一多模态API架构"]'::jsonb,
  '[
    {"title": "大模型开源动态", "items": [
      {"title": "Meta开源Llama-4-R1推理增强模型", "summary": "Meta发布Llama-4-R1，基于强化学习的推理增强版本，在MATH和ARC测试中达到GPT-5同级水平，采用MIT许可证。", "score": 9.5, "url": "https://github.com/meta-llama/llama4", "source": "github", "tags": ["LLM", "开源", "推理"]},
      {"title": "DeepSeek-V4技术报告解读", "summary": "DeepSeek发布V4技术报告，MoE架构370B参数，训练成本仅$5M。HN社区热议开源vs闭源。", "score": 9.3, "url": "https://news.ycombinator.com/item?id=40000001", "source": "hackernews", "tags": ["LLM", "开源", "MoE"]},
      {"title": "OpenAI开源GPT-OSS 7B推理模型", "summary": "OpenAI意外开源GPT-OSS，7B参数，可在MacBook上运行，接近GPT-5-mini水平。社区反应两极化。", "score": 9.0, "url": "https://openai.com/blog/gpt-oss", "source": "rss", "tags": ["LLM", "开源", "推理"]}
    ]},
    {"title": "Agent与智能体框架", "items": [
      {"title": "Google Gemini 3.0首次支持Agent原生能力", "summary": "Gemini 3.0引入Agent API，支持多步工具调用、浏览器自动化和代码执行。MMLU-Pro达92%。", "score": 8.8, "url": "https://blog.google/technology/ai/gemini-3-agent/", "source": "rss", "tags": ["Agent", "Gemini", "多模态"]},
      {"title": "CrewAI v1.0正式版发布", "summary": "CrewAI v1.0新增层级式Agent组织、条件任务流和Human-in-the-Loop审批节点。", "score": 8.0, "url": "https://github.com/crewAIInc/crewAI", "source": "github", "tags": ["Agent", "框架", "开源"]},
      {"title": "AutoGPT发布自主Agent框架v0.6", "summary": "AutoGPT v0.6重构核心调度引擎，支持子Agent动态创建销毁，内存管理优化30%。", "score": 7.5, "url": "https://github.com/Significant-Gravitas/AutoGPT", "source": "github", "tags": ["Agent", "框架", "自主"]}
    ]},
    {"title": "AI工具链与基础设施", "items": [
      {"title": "vLLM v0.7推理吞吐量提升2倍", "summary": "vLLM v0.7引入PagedAttention V3和FP8量化，单卡A100可跑70B模型。", "score": 8.5, "url": "https://github.com/vllm-project/vllm/releases/tag/v0.7.0", "source": "github", "tags": ["推理", "基础设施", "开源"]},
      {"title": "MCP Python SDK正式发布", "summary": "Anthropic开源MCP的Python SDK，标准化AI模型上下文管理接口。", "score": 7.8, "url": "https://github.com/modelcontextprotocol/python-sdk", "source": "github", "tags": ["MCP", "SDK", "标准化"]}
    ]},
    {"title": "AI政策与行业动态", "items": [
      {"title": "欧盟AI法案第二阶段生效", "summary": "覆盖Agent系统、自动驾驶和医疗AI。要求透明性报告和人工监督。违规罚全球营收7%。", "score": 8.2, "url": "https://techcrunch.com/2026/05/24/eu-ai-act-phase-2", "source": "rss", "tags": ["政策", "监管", "欧盟"]},
      {"title": "YC 2026夏季AI初创占比82%", "summary": "230家初创公司中AI相关占82%，集中在Agent工具、垂直应用和基础设施。", "score": 7.0, "url": "https://news.ycombinator.com/item?id=40000008", "source": "hackernews", "tags": ["融资", "创业", "YC"]}
    ]}
  ]'::jsonb,
  '["开源模型与闭源差距缩小至0.3%，Llama-4-R1和DeepSeek-V4成为里程碑",
    "Agent原生能力成为大模型标配，Gemini 3.0和Claude Opus 4.7引领趋势",
    "AI工具链基础设施加速成熟，vLLM/ChromaDB/RAGFlow密集发布大版本",
    "欧盟AI监管正式落地，合规成本将成为AI企业重要考量"]'::jsonb,
  '{"fetched": 30, "scored": 30, "passed": 14, "dedup_removed": 2}'::jsonb
),
('b0000001-0000-0000-0000-000000000002', 'morning', '2026-05-23', 'zh',
  '["Anthropic Claude Opus 4.6发布，Agent能力显著提升",
    "LangChain发布多Agent协作框架",
    "ChromaDB向量数据库达到十亿级规模",
    "HuggingFace发布Transformers v5.0预览版",
    "中国信通院发布Agent产业白皮书"]'::jsonb,
  '[{"title": "大模型动态", "items": [{"title": "Claude Opus 4.6发布", "summary": "Anthropic发布Claude Opus 4.6，Agent能力进一步提升。", "score": 9.0, "url": "https://example.com/claude-4-6", "source": "rss", "tags": ["LLM", "Anthropic"]}]}]'::jsonb,
  '["Agent能力成为大模型核心竞争力"]'::jsonb,
  '{"fetched": 28, "scored": 28, "passed": 12}'::jsonb
),
('b0000001-0000-0000-0000-000000000003', 'evening', '2026-05-23', 'zh',
  '["Dify v1.5多Agent工作流上线",
    "PromptFlow开源引发LLM工具链讨论",
    "斯坦福AI指数2026发布，中国论文数量领先",
    "Next.js 16内置RAG API",
    "Langfuse v3.0实时成本追踪"]'::jsonb,
  '[{"title": "AI工具链", "items": [{"title": "Dify v1.5发布", "summary": "新增多Agent工作流和RAG管道可视化编排。", "score": 8.5, "url": "https://github.com/langgenius/dify", "source": "github", "tags": ["工具", "RAG", "开源"]}]}]'::jsonb,
  '["AI开发工具链日趋成熟，低代码Agent构建成为趋势"]'::jsonb,
  '{"fetched": 25, "scored": 25, "passed": 10}'::jsonb
);

-- ── subscriptions: 5 个假用户（供 C 开发用）───────────────────────
INSERT INTO subscriptions (id, openid, subscribed, morning_enabled, evening_enabled) VALUES
('c0000001-0000-0000-0000-000000000001', 'mock_openid_user_001', true, true, true),
('c0000001-0000-0000-0000-000000000002', 'mock_openid_user_002', true, true, false),
('c0000001-0000-0000-0000-000000000003', 'mock_openid_user_003', true, false, true),
('c0000001-0000-0000-0000-000000000004', 'mock_openid_user_004', false, true, true),
('c0000001-0000-0000-0000-000000000005', 'mock_openid_user_005', true, true, true);

-- ── publish_log: 若干假发布记录（供 D/E 开发用）───────────────────
INSERT INTO publish_log (id, briefing_id, platform, status, platform_url, published_at) VALUES
('d0000001-0000-0000-0000-000000000001', 'b0000001-0000-0000-0000-000000000002', 'weixin_oa', 'success', 'https://mp.weixin.qq.com/s/mock-article-001', '2026-05-23 08:30:00+00'),
('d0000001-0000-0000-0000-000000000002', 'b0000001-0000-0000-0000-000000000002', 'zhihu', 'success', 'https://zhuanlan.zhihu.com/p/mock-001', '2026-05-23 08:35:00+00'),
('d0000001-0000-0000-0000-000000000003', 'b0000001-0000-0000-0000-000000000002', 'csdn', 'failed', NULL, '2026-05-23 08:40:00+00'),
('d0000001-0000-0000-0000-000000000004', 'b0000001-0000-0000-0000-000000000003', 'weixin_oa', 'success', 'https://mp.weixin.qq.com/s/mock-article-002', '2026-05-23 20:30:00+00'),
('d0000001-0000-0000-0000-000000000005', 'b0000001-0000-0000-0000-000000000003', 'zhihu', 'pending', NULL, '2026-05-23 20:35:00+00');

-- ── run_log: 若干假运行记录（供 E 开发用）─────────────────────────
INSERT INTO run_log (id, module, run_type, status, started_at, finished_at, detail) VALUES
('e0000001-0000-0000-0000-000000000001', 'A', 'morning', 'success', '2026-05-23 08:00:00+00', '2026-05-23 08:01:30+00', '{"fetched": 45, "sources": {"github": 15, "hackernews": 10, "rss": 20}}'),
('e0000001-0000-0000-0000-000000000002', 'B', 'morning', 'success', '2026-05-23 08:01:30+00', '2026-05-23 08:04:00+00', '{"scored": 45, "passed": 12}'),
('e0000001-0000-0000-0000-000000000003', 'C', 'morning', 'success', '2026-05-23 08:04:00+00', '2026-05-23 08:04:10+00', '{"pushed": 4, "failed": 0}'),
('e0000001-0000-0000-0000-000000000004', 'D', 'morning', 'success', '2026-05-23 08:04:00+00', '2026-05-23 08:05:00+00', '{"weixin_oa": "success", "zhihu": "success", "csdn": "failed"}'),
('e0000001-0000-0000-0000-000000000005', 'A', 'evening', 'success', '2026-05-23 20:00:00+00', '2026-05-23 20:01:20+00', '{"fetched": 38, "sources": {"github": 12, "hackernews": 8, "rss": 18}}'),
('e0000001-0000-0000-0000-000000000006', 'B', 'evening', 'success', '2026-05-23 20:01:20+00', '2026-05-23 20:03:40+00', '{"scored": 38, "passed": 10}'),
('e0000001-0000-0000-0000-000000000007', 'C', 'evening', 'success', '2026-05-23 20:03:40+00', '2026-05-23 20:03:50+00', '{"pushed": 3, "failed": 1}'),
('e0000001-0000-0000-0000-000000000008', 'D', 'evening', 'failed', '2026-05-23 20:03:40+00', '2026-05-23 20:04:00+00', '{"error": "weixin_oa: IP not in whitelist"}');
