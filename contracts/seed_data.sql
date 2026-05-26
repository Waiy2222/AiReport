-- ============================================================
-- AI 璧勮��鏃╂姤/鏅氭姤鏅鸿兘浣� 路 绉嶅瓙鏁版嵁
-- 璁╂瘡涓�妯″潡鎷垮埌鍗冲彲鐙�绔嬪紑鍙戯紝涓嶉渶瑕佺瓑鍏朵粬妯″潡瀹屾垚
-- ============================================================

-- 鈹�鈹� raw_items: 30鏉″亣 AI 璧勮��锛堟ā鎷� A 妯″潡鎶撳彇缁撴灉锛屼緵 B 寮�鍙戠敤锛夆攢鈹�鈹�鈹�
INSERT INTO raw_items (id, source, title, url, content, author, published_at, batch_id) VALUES
('a0000001-0000-0000-0000-000000000001', 'github', 'LangChain发布v0.3版本，新增多Agent协作能力', 'https://github.com/langchain-ai/langchain/releases/tag/v0.3.0', 'LangChain v0.3.0 正式发布，新增MultiAgentCoordinator类，支持多个Agent之间的消息传递和任务分配。', 'langchain-ai', '2026-05-24 02:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000002', 'github', 'Open Source LLM Tool Calling Framework: Gorilla v2.0', 'https://github.com/ShishirPatil/gorilla', 'Gorilla v2.0 发布，新增对Claude、Gemini、DeepSeek等模型的tool calling支持，准确率提升至95%。', 'ShishirPatil', '2026-05-24 04:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000003', 'github', 'Ollama Stars突破10万，成为最流行的本地LLM运行时', 'https://github.com/ollama/ollama', 'Ollama在GitHub上Stars突破10万，支持macOS/Linux/Windows三平台，最新版本新增对DeepSeek-V4的本地运行支持。', 'ollama', '2026-05-23 18:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000004', 'github', 'AutoGPT发布自主Agent框架v0.6', 'https://github.com/Significant-Gravitas/AutoGPT', 'AutoGPT v0.6 重构了核心调度引擎，支持子Agent的动态创建和销毁，内存管理优化30%。', 'Significant-Gravitas', '2026-05-24 01:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000005', 'github', 'vLLM发布v0.7.0，推理吞吐量提升2倍', 'https://github.com/vllm-project/vllm/releases/tag/v0.7.0', 'vLLM v0.7.0引入PagedAttention V3和FP8量化，单卡A100可跑70B模型，吞吐量相较v0.6提升2倍。', 'vllm-project', '2026-05-24 06:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000006', 'github', 'MCP (Model Context Protocol) Python SDK正式发布', 'https://github.com/modelcontextprotocol/python-sdk', 'Anthropic开源MCP的Python SDK，提供标准化的AI模型上下文管理接口，支持多Provider切换。', 'modelcontextprotocol', '2026-05-23 14:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000007', 'github', 'ChromaDB发布向量数据库v1.0', 'https://github.com/chroma-core/chroma', 'ChromaDB v1.0正式版发布，支持十亿级向量检索，新增HNSW索引，查询延迟降至5ms。', 'chroma-core', '2026-05-24 00:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000008', 'github', 'HuggingFace Transformers v5.0架构重构', 'https://github.com/huggingface/transformers', 'Transformers v5.0发布，统一了LLM、多模态和扩散模型的API，引入AutoModelV2自动选型机制。', 'huggingface', '2026-05-23 22:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000009', 'github', 'Meta开源Llama-4-R1推理增强模型', 'https://github.com/meta-llama/llama4', 'Meta发布Llama-4-R1，基于强化学习的推理增强版本，在MATH和ARC测试中达到GPT-5同级水平，采用MIT许可证。', 'meta-llama', '2026-05-24 03:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000010', 'github', 'Dify发布AI应用构建平台v1.5', 'https://github.com/langgenius/dify', 'Dify v1.5新增多Agent工作流、RAG管道可视化编排、知识库多格式支持（PDF/Word/Notion/网页）', 'langgenius', '2026-05-23 20:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000011', 'hackernews', 'DeepSeek-V4:中国首个全开源MoE大模型的技术报告解读', 'https://news.ycombinator.com/item?id=40000001', 'DeepSeek发布V4技术报告，MoE架构370B参数，训练成本仅$5M，多项基准超过GPT-4o。HN社区热烈讨论开源vs闭源的未来。', 'tech_review', '2026-05-24 05:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000012', 'hackernews', 'Anthropic发布Claude Opus 4.7，编程能力大幅提升', 'https://news.ycombinator.com/item?id=40000002', 'Claude Opus 4.7在SWE-Bench Verified上达到85%准确率，超越所有竞品。支持200K上下文窗口。', 'ai_explorer', '2026-05-24 07:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000013', 'hackernews', '为什么我们决定将所有微服务迁移到单体应用', 'https://news.ycombinator.com/item?id=40000003', '一位CTO分享将AI创业公司的微服务架构迁移到单体的经验，引发了关于过早优化与工程复杂度的讨论。', 'cto_startup', '2026-05-23 16:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000014', 'hackernews', 'OpenAI被曝正在开发全新推理架构"Strawberry"', 'https://news.ycombinator.com/item?id=40000004', '据The Information报道，OpenAI内部正在开发代号Strawberry的新型推理架构，可能在数学和编程方面有质的飞跃。', 'insider_news', '2026-05-24 08:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000015', 'hackernews', 'Show HN:我做了个开源AI代码审查工具，用本地LLM保护隐私', 'https://news.ycombinator.com/item?id=40000005', '作者分享基于Ollama+Llama-4的开源代码审查工具，完全本地运行，支持GitHub/GitLab集成，已有500+Stars。', 'indie_dev', '2026-05-23 21:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000016', 'rss', 'Google DeepMind发布Gemini 3.0，首次支持Agent原生能力', 'https://blog.google/technology/ai/gemini-3-agent/', 'Gemini 3.0引入Agent API，支持多步工具调用、浏览器自动化和代码执行。在MMLU-Pro上达到92%。', 'Google AI Blog', '2026-05-24 00:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000017', 'rss', '中国信通院发布《2026年AI Agent产业白皮书》', 'https://www.caict.ac.cn/ai-agent-2026', '白皮书指出2026年全球Agent市场规模突破200亿美元，中国企业级Agent应用增长最快，智能客服和代码助手是两大突破口。', '中国信通院', '2026-05-24 06:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000018', 'rss', 'MIT研究团队提出新的Agent评估框架AgentBench V2', 'https://news.mit.edu/2026/agent-bench-v2', 'MIT CSAIL发布AgentBench V2，覆盖200+真实任务场景，包括代码、网络、文件操作等，成为Agent能力评估新标准。', 'MIT News', '2026-05-23 15:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000019', 'rss', 'OpenAI开源GPT-OSS：一个可在消费级硬件上运行的推理模型', 'https://openai.com/blog/gpt-oss', 'OpenAI意外开源GPT-OSS，7B参数，可在MacBook上运行，在数学和代码方面接近GPT-5-mini水平。社区反应两极化。', 'OpenAI Blog', '2026-05-24 04:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000020', 'rss', 'Next.js 16发布：AI-first框架，内置RAG API', 'https://nextjs.org/blog/next-16', 'Vercel发布Next.js 16，首次内置RAG API和AI Agent路由，支持Streaming SSR与Edge Runtime的深度融合。', 'Vercel Blog', '2026-05-23 19:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000021', 'github', 'CrewAI多Agent框架发布v1.0正式版', 'https://github.com/crewAIInc/crewAI', 'CrewAI v1.0发布，新增层级式Agent组织、条件任务流和Human-in-the-Loop审批节点，企业级特性完善。', 'crewAIInc', '2026-05-24 05:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000022', 'hackernews', '微软开源PromptFlow：LLM应用的可视化开发工具', 'https://news.ycombinator.com/item?id=40000006', '微软将内部PromptFlow工具开源，支持可视化编排LLM链、评估和部署。社区对比LangChain和Dify的方案优劣。', 'ms_dev', '2026-05-23 23:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000023', 'rss', '斯坦福发布AI指数2026年度报告', 'https://aiindex.stanford.edu/report/2026/', '斯坦福HAI发布2026年AI指数报告：中国在AI论文数量和专利方面领先，美国在模型能力和投资方面领先。开源模型与闭源模型差距缩小至0.3%。', 'Stanford HAI', '2026-05-24 01:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000024', 'github', 'RAGFlow开源RAG引擎发布v2.0', 'https://github.com/infiniflow/ragflow', 'RAGFlow v2.0新增Graph RAG、多模态检索和Agentic RAG能力，支持非结构化文档深度理解，企业级部署方案完善。', 'infiniflow', '2026-05-23 17:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000025', 'hackernews', 'AI编程助手市场格局分析与2026趋势预测', 'https://news.ycombinator.com/item?id=40000007', '一位资深开发者对GitHub Copilot、Cursor、Claude Code、Windsurf等7款AI编程工具进行深度横评，引发社区对IDE未来的讨论。', 'dev_analyst', '2026-05-24 06:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000026', 'rss', '阿里通义千问发布Qwen-3-Max，中文能力全面领先', 'https://tongyi.aliyun.com/blog/qwen-3-max', '通义千问Qwen-3-Max发布，在C-Eval、CMMLU等中文基准测试中全面领先，支持100万字长上下文，API价格仅为GPT-5的1/10。', '阿里云', '2026-05-24 02:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000027', 'github', 'Langfuse发布LLM可观测性平台v3.0', 'https://github.com/langfuse/langfuse', 'Langfuse v3.0支持实时Token成本追踪、Agent调用链可视化、自动化评估和告警，支持自部署和云服务两种模式。', 'langfuse', '2026-05-23 13:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000028', 'hackernews', 'YC 2026夏季批次：AI初创公司占比首次超过80%', 'https://news.ycombinator.com/item?id=40000008', 'Y Combinator 2026年夏季批次共有230家初创公司，其中AI相关占82%。主要是AI Agent工具、垂直行业AI应用和AI基础设施。', 'yc_observer', '2026-05-24 07:30:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000029', 'rss', '欧盟AI法案第二阶段正式实施：高风险AI系统需强制备案', 'https://techcrunch.com/2026/05/24/eu-ai-act-phase-2', '欧盟AI法案第二阶段生效，覆盖Agent系统、自动驾驶和医疗AI。要求透明性报告、人工监督机制和风险评估。违规最高罚全球营收的7%。', 'TechCrunch', '2026-05-24 08:00:00+00', 'a0000000-0000-0000-0000-000000000001'),
('a0000001-0000-0000-0000-000000000030', 'github', 'PaddlePaddle发布飞桨3.0：中文AI开发者的首选框架', 'https://github.com/PaddlePaddle/Paddle', '百度飞桨3.0发布，全面支持大模型训练和推理，新增AutoParallel分布式训练，中文NLP预训练模型库扩充至500+。', 'PaddlePaddle', '2026-05-24 00:00:00+00', 'a0000000-0000-0000-0000-000000000001');

-- 鈹�鈹� briefings: 3 鏈熷亣绠�鎶ワ紙妯℃嫙 B 妯″潡杈撳嚭锛屼緵 C/D 寮�鍙戠敤锛夆攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�
INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats) VALUES
('b0000001-0000-0000-0000-000000000001', 'morning', '2026-05-24', 'zh',
  '["DeepSeek-V4鎶�鏈�鎶ュ憡寮曞彂鍏ㄧ悆鍏虫敞锛孧oE鏋舵瀯370B鍙傛暟寮�婧愶紝璁�缁冩垚鏈�浠�500涓囩編鍏�",
    "Meta寮�婧怢lama-4-R1鎺ㄧ悊澧炲己妯″瀷锛孧IT璁稿彲璇侊紝澶氶」鍩哄噯杈綠PT-5鍚岀骇",
    "Anthropic鍙戝竷Claude Opus 4.7锛孲WE-Bench Verified鍑嗙‘鐜�85%",
    "OpenAI鎰忓�栧紑婧怗PT-OSS 7B鎺ㄧ悊妯″瀷锛屽彲鍦ㄦ秷璐圭骇纭�浠惰繍琛�",
    "Google DeepMind鍙戝竷Gemini 3.0锛岄�栨�″師鐢熸敮鎸丄gent API",
    "娆х洘AI娉曟�堢��浜岄樁娈电敓鏁堬紝楂橀�庨櫓AI绯荤粺闇�寮哄埗澶囨��",
    "YC 2026澶忓�ｆ壒娆�AI鍒濆垱鍗犳瘮82%锛孉gent宸ュ叿鍜屽瀭鐩村簲鐢ㄦ垚鐑�鐐�",
    "vLLM v0.7鎺ㄧ悊鍚炲悙閲忔彁鍗�2鍊嶏紝FP8閲忓寲鏀�鎸�70B妯″瀷鍗曞崱閮ㄧ讲",
    "CrewAI v1.0鍜孉utoGPT v0.6鍚屾棩鍙戝竷锛屽�欰gent妗嗘灦绔炰簤鐧界儹鍖�",
    "HuggingFace Transformers v5.0缁熶竴澶氭ā鎬丄PI鏋舵瀯"]'::jsonb,
  '[
    {"title": "澶фā鍨嬪紑婧愬姩鎬�", "items": [
      {"title": "Meta寮�婧怢lama-4-R1鎺ㄧ悊澧炲己妯″瀷", "summary": "Meta鍙戝竷Llama-4-R1锛屽熀浜庡己鍖栧�︿範鐨勬帹鐞嗗�炲己鐗堟湰锛屽湪MATH鍜孉RC娴嬭瘯涓�杈惧埌GPT-5鍚岀骇姘村钩锛岄噰鐢∕IT璁稿彲璇併��", "score": 9.5, "url": "https://github.com/meta-llama/llama4", "source": "github", "tags": ["LLM", "寮�婧�", "鎺ㄧ悊"]},
      {"title": "DeepSeek-V4鎶�鏈�鎶ュ憡瑙ｈ��", "summary": "DeepSeek鍙戝竷V4鎶�鏈�鎶ュ憡锛孧oE鏋舵瀯370B鍙傛暟锛岃��缁冩垚鏈�浠�$5M銆侶N绀惧尯鐑�璁�寮�婧恦s闂�婧愩��", "score": 9.3, "url": "https://news.ycombinator.com/item?id=40000001", "source": "hackernews", "tags": ["LLM", "寮�婧�", "MoE"]},
      {"title": "OpenAI寮�婧怗PT-OSS 7B鎺ㄧ悊妯″瀷", "summary": "OpenAI鎰忓�栧紑婧怗PT-OSS锛�7B鍙傛暟锛屽彲鍦∕acBook涓婅繍琛岋紝鎺ヨ繎GPT-5-mini姘村钩銆傜ぞ鍖哄弽搴斾袱鏋佸寲銆�", "score": 9.0, "url": "https://openai.com/blog/gpt-oss", "source": "rss", "tags": ["LLM", "寮�婧�", "鎺ㄧ悊"]}
    ]},
    {"title": "Agent涓庢櫤鑳戒綋妗嗘灦", "items": [
      {"title": "Google Gemini 3.0棣栨�℃敮鎸丄gent鍘熺敓鑳藉姏", "summary": "Gemini 3.0寮曞叆Agent API锛屾敮鎸佸�氭�ュ伐鍏疯皟鐢ㄣ�佹祻瑙堝櫒鑷�鍔ㄥ寲鍜屼唬鐮佹墽琛屻�侻MLU-Pro杈�92%銆�", "score": 8.8, "url": "https://blog.google/technology/ai/gemini-3-agent/", "source": "rss", "tags": ["Agent", "Gemini", "澶氭ā鎬�"]},
      {"title": "CrewAI v1.0姝ｅ紡鐗堝彂甯�", "summary": "CrewAI v1.0鏂板�炲眰绾у紡Agent缁勭粐銆佹潯浠朵换鍔℃祦鍜孒uman-in-the-Loop瀹℃壒鑺傜偣銆�", "score": 8.0, "url": "https://github.com/crewAIInc/crewAI", "source": "github", "tags": ["Agent", "妗嗘灦", "寮�婧�"]},
      {"title": "AutoGPT鍙戝竷鑷�涓籄gent妗嗘灦v0.6", "summary": "AutoGPT v0.6閲嶆瀯鏍稿績璋冨害寮曟搸锛屾敮鎸佸瓙Agent鍔ㄦ�佸垱寤洪攢姣侊紝鍐呭瓨绠＄悊浼樺寲30%銆�", "score": 7.5, "url": "https://github.com/Significant-Gravitas/AutoGPT", "source": "github", "tags": ["Agent", "妗嗘灦", "鑷�涓�"]}
    ]},
    {"title": "AI宸ュ叿閾句笌鍩虹��璁炬柦", "items": [
      {"title": "vLLM v0.7鎺ㄧ悊鍚炲悙閲忔彁鍗�2鍊�", "summary": "vLLM v0.7寮曞叆PagedAttention V3鍜孎P8閲忓寲锛屽崟鍗�A100鍙�璺�70B妯″瀷銆�", "score": 8.5, "url": "https://github.com/vllm-project/vllm/releases/tag/v0.7.0", "source": "github", "tags": ["鎺ㄧ悊", "鍩虹��璁炬柦", "寮�婧�"]},
      {"title": "MCP Python SDK姝ｅ紡鍙戝竷", "summary": "Anthropic寮�婧怣CP鐨凱ython SDK锛屾爣鍑嗗寲AI妯″瀷涓婁笅鏂囩�＄悊鎺ュ彛銆�", "score": 7.8, "url": "https://github.com/modelcontextprotocol/python-sdk", "source": "github", "tags": ["MCP", "SDK", "鏍囧噯鍖�"]}
    ]},
    {"title": "AI鏀跨瓥涓庤�屼笟鍔ㄦ��", "items": [
      {"title": "娆х洘AI娉曟�堢��浜岄樁娈电敓鏁�", "summary": "瑕嗙洊Agent绯荤粺銆佽嚜鍔ㄩ┚椹跺拰鍖荤枟AI銆傝�佹眰閫忔槑鎬ф姤鍛婂拰浜哄伐鐩戠潱銆傝繚瑙勭綒鍏ㄧ悆钀ユ敹7%銆�", "score": 8.2, "url": "https://techcrunch.com/2026/05/24/eu-ai-act-phase-2", "source": "rss", "tags": ["鏀跨瓥", "鐩戠��", "娆х洘"]},
      {"title": "YC 2026澶忓��AI鍒濆垱鍗犳瘮82%", "summary": "230瀹跺垵鍒涘叕鍙镐腑AI鐩稿叧鍗�82%锛岄泦涓�鍦ˋgent宸ュ叿銆佸瀭鐩村簲鐢ㄥ拰鍩虹��璁炬柦銆�", "score": 7.0, "url": "https://news.ycombinator.com/item?id=40000008", "source": "hackernews", "tags": ["铻嶈祫", "鍒涗笟", "YC"]}
    ]}
  ]'::jsonb,
  '["寮�婧愭ā鍨嬩笌闂�婧愬樊璺濈缉灏忚嚦0.3%锛孡lama-4-R1鍜孌eepSeek-V4鎴愪负閲岀▼纰�",
    "Agent鍘熺敓鑳藉姏鎴愪负澶фā鍨嬫爣閰嶏紝Gemini 3.0鍜孋laude Opus 4.7寮曢�嗚秼鍔�",
    "AI宸ュ叿閾惧熀纭�璁炬柦鍔犻�熸垚鐔燂紝vLLM/ChromaDB/RAGFlow瀵嗛泦鍙戝竷澶х増鏈�",
    "娆х洘AI鐩戠�℃�ｅ紡钀藉湴锛屽悎瑙勬垚鏈�灏嗘垚涓篈I浼佷笟閲嶈�佽�冮噺"]'::jsonb,
  '{"fetched": 30, "scored": 30, "passed": 14, "dedup_removed": 2}'::jsonb
),
('b0000001-0000-0000-0000-000000000002', 'morning', '2026-05-23', 'zh',
  '["Anthropic Claude Opus 4.6鍙戝竷锛孉gent鑳藉姏鏄捐憲鎻愬崌",
    "LangChain鍙戝竷澶欰gent鍗忎綔妗嗘灦",
    "ChromaDB鍚戦噺鏁版嵁搴撹揪鍒板崄浜跨骇瑙勬ā",
    "HuggingFace鍙戝竷Transformers v5.0棰勮�堢増",
    "涓�鍥戒俊閫氶櫌鍙戝竷Agent浜т笟鐧界毊涔�"]'::jsonb,
  '[{"title": "澶фā鍨嬪姩鎬�", "items": [{"title": "Claude Opus 4.6鍙戝竷", "summary": "Anthropic鍙戝竷Claude Opus 4.6锛孉gent鑳藉姏杩涗竴姝ユ彁鍗囥��", "score": 9.0, "url": "https://example.com/claude-4-6", "source": "rss", "tags": ["LLM", "Anthropic"]}]}]'::jsonb,
  '["Agent鑳藉姏鎴愪负澶фā鍨嬫牳蹇冪珵浜夊姏"]'::jsonb,
  '{"fetched": 28, "scored": 28, "passed": 12}'::jsonb
),
('b0000001-0000-0000-0000-000000000003', 'evening', '2026-05-23', 'zh',
  '["Dify v1.5澶欰gent宸ヤ綔娴佷笂绾�",
    "PromptFlow寮�婧愬紩鍙慙LM宸ュ叿閾捐�ㄨ��",
    "鏂�鍧︾�廇I鎸囨暟2026鍙戝竷锛屼腑鍥借�烘枃鏁伴噺棰嗗厛",
    "Next.js 16鍐呯疆RAG API",
    "Langfuse v3.0瀹炴椂鎴愭湰杩借釜"]'::jsonb,
  '[{"title": "AI宸ュ叿閾�", "items": [{"title": "Dify v1.5鍙戝竷", "summary": "鏂板�炲�欰gent宸ヤ綔娴佸拰RAG绠￠亾鍙�瑙嗗寲缂栨帓銆�", "score": 8.5, "url": "https://github.com/langgenius/dify", "source": "github", "tags": ["宸ュ叿", "RAG", "寮�婧�"]}]}]'::jsonb,
  '["AI寮�鍙戝伐鍏烽摼鏃ヨ秼鎴愮啛锛屼綆浠ｇ爜Agent鏋勫缓鎴愪负瓒嬪娍"]'::jsonb,
  '{"fetched": 25, "scored": 25, "passed": 10}'::jsonb
);

-- 鈹�鈹� subscriptions: 5 涓�鍋囩敤鎴凤紙渚� C 寮�鍙戠敤锛夆攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�
INSERT INTO subscriptions (id, openid, subscribed, morning_enabled, evening_enabled) VALUES
('c0000001-0000-0000-0000-000000000001', 'mock_openid_user_001', true, true, true),
('c0000001-0000-0000-0000-000000000002', 'mock_openid_user_002', true, true, false),
('c0000001-0000-0000-0000-000000000003', 'mock_openid_user_003', true, false, true),
('c0000001-0000-0000-0000-000000000004', 'mock_openid_user_004', false, true, true),
('c0000001-0000-0000-0000-000000000005', 'mock_openid_user_005', true, true, true);

-- 鈹�鈹� publish_log: 鑻ュ共鍋囧彂甯冭�板綍锛堜緵 D/E 寮�鍙戠敤锛夆攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�
INSERT INTO publish_log (id, briefing_id, platform, status, platform_url, published_at) VALUES
('d0000001-0000-0000-0000-000000000001', 'b0000001-0000-0000-0000-000000000002', 'weixin_oa', 'success', 'https://mp.weixin.qq.com/s/mock-article-001', '2026-05-23 08:30:00+00'),
('d0000001-0000-0000-0000-000000000002', 'b0000001-0000-0000-0000-000000000002', 'zhihu', 'success', 'https://zhuanlan.zhihu.com/p/mock-001', '2026-05-23 08:35:00+00'),
('d0000001-0000-0000-0000-000000000003', 'b0000001-0000-0000-0000-000000000002', 'csdn', 'failed', NULL, '2026-05-23 08:40:00+00'),
('d0000001-0000-0000-0000-000000000004', 'b0000001-0000-0000-0000-000000000003', 'weixin_oa', 'success', 'https://mp.weixin.qq.com/s/mock-article-002', '2026-05-23 20:30:00+00'),
('d0000001-0000-0000-0000-000000000005', 'b0000001-0000-0000-0000-000000000003', 'zhihu', 'pending', NULL, '2026-05-23 20:35:00+00');

-- 鈹�鈹� run_log: 鑻ュ共鍋囪繍琛岃�板綍锛堜緵 E 寮�鍙戠敤锛夆攢鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�鈹�
INSERT INTO run_log (id, module, run_type, status, started_at, finished_at, detail) VALUES
('e0000001-0000-0000-0000-000000000001', 'A', 'morning', 'success', '2026-05-23 08:00:00+00', '2026-05-23 08:01:30+00', '{"fetched": 45, "sources": {"github": 15, "hackernews": 10, "rss": 20}}'),
('e0000001-0000-0000-0000-000000000002', 'B', 'morning', 'success', '2026-05-23 08:01:30+00', '2026-05-23 08:04:00+00', '{"scored": 45, "passed": 12}'),
('e0000001-0000-0000-0000-000000000003', 'C', 'morning', 'success', '2026-05-23 08:04:00+00', '2026-05-23 08:04:10+00', '{"pushed": 4, "failed": 0}'),
('e0000001-0000-0000-0000-000000000004', 'D', 'morning', 'success', '2026-05-23 08:04:00+00', '2026-05-23 08:05:00+00', '{"weixin_oa": "success", "zhihu": "success", "csdn": "failed"}'),
('e0000001-0000-0000-0000-000000000005', 'A', 'evening', 'success', '2026-05-23 20:00:00+00', '2026-05-23 20:01:20+00', '{"fetched": 38, "sources": {"github": 12, "hackernews": 8, "rss": 18}}'),
('e0000001-0000-0000-0000-000000000006', 'B', 'evening', 'success', '2026-05-23 20:01:20+00', '2026-05-23 20:03:40+00', '{"scored": 38, "passed": 10}'),
('e0000001-0000-0000-0000-000000000007', 'C', 'evening', 'success', '2026-05-23 20:03:40+00', '2026-05-23 20:03:50+00', '{"pushed": 3, "failed": 1}'),
('e0000001-0000-0000-0000-000000000008', 'D', 'evening', 'failed', '2026-05-23 20:03:40+00', '2026-05-23 20:04:00+00', '{"error": "weixin_oa: IP not in whitelist"}');
