"""重新灌入正确编码的简报种子数据"""
import asyncio
import json
from datetime import date
import asyncpg

DSN = "postgresql://postgres:postgres@localhost:5432/ai_news"

async def seed():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE briefings CASCADE;")

        # 简报1: 早报 2026-05-24
        tl_dr_1 = [
            "DeepSeek-V4技术报告引发全球关注，MoE架构370B参数开源，训练成本仅500万美元",
            "Meta开源Llama-4-R1推理增强模型，MIT许可证，多项基准达GPT-5同级",
            "Anthropic发布Claude Opus 4.7，SWE-Bench Verified准确率达85%",
            "OpenAI意外开源GPT-OSS 7B推理模型，可在消费级硬件运行",
            "Google DeepMind发布Gemini 3.0，首次原生支持Agent API",
            "欧盟AI法案第二阶段生效，高风险AI系统需强制备案",
            "YC 2026夏季批次AI初创占比82%，Agent工具和垂直应用成热点",
            "vLLM v0.7推理吞吐量提升2倍，FP8量化支持70B模型单卡部署",
            "CrewAI v1.0和AutoGPT v0.6同日发布，Agent框架竞争白热化",
            "HuggingFace Transformers v5.0统一多模态API架构",
        ]
        sections_1 = [
            {"title": "大模型开源动态", "items": [
                {"title": "Meta开源Llama-4-R1推理增强模型", "summary": "Meta发布Llama-4-R1，基于强化学习的推理增强版本，在MATH和ARC测试中达到GPT-5同级水平，采用MIT许可证。", "score": 9.5, "url": "https://github.com/meta-llama/llama4", "source": "github", "tags": ["LLM", "开源", "推理"]},
                {"title": "DeepSeek-V4技术报告解读", "summary": "DeepSeek发布V4技术报告，MoE架构370B参数，训练成本仅$5M。HN社区热议开源vs闭源。", "score": 9.3, "url": "https://news.ycombinator.com/item?id=40000001", "source": "hackernews", "tags": ["LLM", "开源", "MoE"]},
                {"title": "OpenAI开源GPT-OSS 7B推理模型", "summary": "OpenAI意外开源GPT-OSS，7B参数，可在MacBook上运行，接近GPT-5-mini水平。", "score": 9.0, "url": "https://openai.com/blog/gpt-oss", "source": "rss", "tags": ["LLM", "开源", "推理"]},
            ]},
            {"title": "Agent与智能体框架", "items": [
                {"title": "Google Gemini 3.0首次支持Agent原生能力", "summary": "Gemini 3.0引入Agent API，支持多步工具调用、浏览器自动化和代码执行。MMLU-Pro达92%。", "score": 8.8, "url": "https://blog.google/technology/ai/gemini-3-agent/", "source": "rss", "tags": ["Agent", "Gemini", "多模态"]},
                {"title": "CrewAI v1.0正式版发布", "summary": "CrewAI v1.0新增层级式Agent组织、条件任务流和Human-in-the-Loop审批节点。", "score": 8.0, "url": "https://github.com/crewAIInc/crewAI", "source": "github", "tags": ["Agent", "框架", "开源"]},
                {"title": "AutoGPT发布自主Agent框架v0.6", "summary": "AutoGPT v0.6重构核心调度引擎，支持子Agent动态创建销毁，内存管理优化30%。", "score": 7.5, "url": "https://github.com/Significant-Gravitas/AutoGPT", "source": "github", "tags": ["Agent", "框架", "自主"]},
            ]},
            {"title": "AI工具链与基础设施", "items": [
                {"title": "vLLM v0.7推理吞吐量提升2倍", "summary": "vLLM v0.7引入PagedAttention V3和FP8量化，单卡A100可跑70B模型。", "score": 8.5, "url": "https://github.com/vllm-project/vllm/releases/tag/v0.7.0", "source": "github", "tags": ["推理", "基础设施", "开源"]},
                {"title": "MCP Python SDK正式发布", "summary": "Anthropic开源MCP的Python SDK，标准化AI模型上下文管理接口。", "score": 7.8, "url": "https://github.com/modelcontextprotocol/python-sdk", "source": "github", "tags": ["MCP", "SDK", "标准化"]},
            ]},
            {"title": "AI政策与行业动态", "items": [
                {"title": "欧盟AI法案第二阶段生效", "summary": "覆盖Agent系统、自动驾驶和医疗AI。要求透明性报告和人工监督。违规罚全球营收7%。", "score": 8.2, "url": "https://techcrunch.com/2026/05/24/eu-ai-act-phase-2", "source": "rss", "tags": ["政策", "监管", "欧盟"]},
                {"title": "YC 2026夏季AI初创占比82%", "summary": "230家初创公司中AI相关占82%，集中在Agent工具、垂直应用和基础设施。", "score": 7.0, "url": "https://news.ycombinator.com/item?id=40000008", "source": "hackernews", "tags": ["融资", "创业", "YC"]},
            ]},
        ]
        takeaways_1 = [
            "开源模型与闭源差距缩小至0.3%，Llama-4-R1和DeepSeek-V4成为里程碑",
            "Agent原生能力成为大模型标配，Gemini 3.0和Claude Opus 4.7引领趋势",
            "AI工具链基础设施加速成熟，vLLM/ChromaDB/RAGFlow密集发布大版本",
            "欧盟AI监管正式落地，合规成本将成为AI企业重要考量",
        ]
        stats_1 = {"fetched": 30, "scored": 30, "passed": 14, "dedup_removed": 2}

        await conn.execute(
            """INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)""",
            "b0000001-0000-0000-0000-000000000001", "morning", date(2026, 5, 24), "zh",
            json.dumps(tl_dr_1, ensure_ascii=False),
            json.dumps(sections_1, ensure_ascii=False),
            json.dumps(takeaways_1, ensure_ascii=False),
            json.dumps(stats_1, ensure_ascii=False),
        )

        # 简报2: 早报 2026-05-23
        tl_dr_2 = [
            "Anthropic Claude Opus 4.6发布，Agent能力显著提升",
            "LangChain发布多Agent协作框架",
            "ChromaDB向量数据库达到十亿级规模",
            "HuggingFace发布Transformers v5.0预览版",
            "中国信通院发布Agent产业白皮书",
        ]
        sections_2 = [{"title": "大模型动态", "items": [{"title": "Claude Opus 4.6发布", "summary": "Anthropic发布Claude Opus 4.6，Agent能力进一步提升。", "score": 9.0, "url": "https://example.com/claude-4-6", "source": "rss", "tags": ["LLM", "Anthropic"]}]}]

        await conn.execute(
            """INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)""",
            "b0000001-0000-0000-0000-000000000002", "morning", date(2026, 5, 23), "zh",
            json.dumps(tl_dr_2, ensure_ascii=False),
            json.dumps(sections_2, ensure_ascii=False),
            json.dumps(["Agent能力成为大模型核心竞争力"], ensure_ascii=False),
            json.dumps({"fetched": 28, "scored": 28, "passed": 12}, ensure_ascii=False),
        )

        # 简报3: 晚报 2026-05-23
        tl_dr_3 = [
            "Dify v1.5多Agent工作流上线",
            "PromptFlow开源引发LLM工具链讨论",
            "斯坦福AI指数2026发布，中国论文数量领先",
            "Next.js 16内置RAG API",
            "Langfuse v3.0实时成本追踪",
        ]
        sections_3 = [{"title": "AI工具链", "items": [{"title": "Dify v1.5发布", "summary": "新增多Agent工作流和RAG管道可视化编排。", "score": 8.5, "url": "https://github.com/langgenius/dify", "source": "github", "tags": ["工具", "RAG", "开源"]}]}]

        await conn.execute(
            """INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb)""",
            "b0000001-0000-0000-0000-000000000003", "evening", date(2026, 5, 23), "zh",
            json.dumps(tl_dr_3, ensure_ascii=False),
            json.dumps(sections_3, ensure_ascii=False),
            json.dumps(["AI开发工具链日趋成熟，低代码Agent构建成为趋势"], ensure_ascii=False),
            json.dumps({"fetched": 25, "scored": 25, "passed": 10}, ensure_ascii=False),
        )

    # 验证
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM briefings")
        row = await conn.fetchrow("SELECT tl_dr FROM briefings WHERE type='morning' ORDER BY date DESC LIMIT 1")
        tl_dr = json.loads(row["tl_dr"])
        print(f"briefings: {count} rows")
        print(f"最新早报 tl_dr[0]: {tl_dr[0]}")
    await pool.close()
    print("Done!")

asyncio.run(seed())
