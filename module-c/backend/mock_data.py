"""内置假数据 — 无 PostgreSQL 时自动使用，与 seed_data.sql 一致"""
import copy
from datetime import datetime, timedelta

BRIEFINGS = [
    {
        "id": "b0000001-0000-0000-0000-000000000001",
        "type": "morning",
        "date": "2026-05-24",
        "language": "zh",
        "tl_dr": [
            "DeepSeek-V4技术报告引发全球关注，MoE架构370B参数开源，训练成本仅500万美元",
            "Meta开源Llama-4-R1推理增强模型，MIT许可证，多项基准达GPT-5同级",
            "Anthropic发布Claude Opus 4.7，SWE-Bench Verified准确率85%",
            "OpenAI意外开源GPT-OSS 7B推理模型，可在消费级硬件运行",
            "Google DeepMind发布Gemini 3.0，首次原生支持Agent API",
            "欧盟AI法案第二阶段生效，高风险AI系统需强制备案",
            "YC 2026夏季批次AI初创占比82%，Agent工具和垂直应用成热点",
            "vLLM v0.7推理吞吐量提升2倍，FP8量化支持70B模型单卡部署",
            "CrewAI v1.0和AutoGPT v0.6同日发布，多Agent框架竞争白热化",
            "HuggingFace Transformers v5.0统一多模态API架构",
        ],
        "sections": [
            {
                "title": "大模型开源动态",
                "items": [
                    {
                        "title": "Meta开源Llama-4-R1推理增强模型",
                        "summary": "Meta发布Llama-4-R1，基于强化学习的推理增强版本，在MATH和ARC测试中达到GPT-5同级水平，采用MIT许可证。",
                        "score": 9.5,
                        "url": "https://github.com/meta-llama/llama4",
                        "source": "github",
                        "tags": ["LLM", "开源", "推理"],
                    },
                    {
                        "title": "DeepSeek-V4技术报告解读",
                        "summary": "DeepSeek发布V4技术报告，MoE架构370B参数，训练成本仅$5M。HN社区热议开源vs闭源。",
                        "score": 9.3,
                        "url": "https://news.ycombinator.com/item?id=40000001",
                        "source": "hackernews",
                        "tags": ["LLM", "开源", "MoE"],
                    },
                    {
                        "title": "OpenAI开源GPT-OSS 7B推理模型",
                        "summary": "OpenAI意外开源GPT-OSS，7B参数，可在MacBook上运行，接近GPT-5-mini水平。",
                        "score": 9.0,
                        "url": "https://openai.com/blog/gpt-oss",
                        "source": "rss",
                        "tags": ["LLM", "开源", "推理"],
                    },
                ],
            },
            {
                "title": "Agent与智能体框架",
                "items": [
                    {
                        "title": "Google Gemini 3.0首次支持Agent原生能力",
                        "summary": "Gemini 3.0引入Agent API，支持多步工具调用、浏览器自动化和代码执行。MMLU-Pro达92%。",
                        "score": 8.8,
                        "url": "https://blog.google/technology/ai/gemini-3-agent/",
                        "source": "rss",
                        "tags": ["Agent", "Gemini", "多模态"],
                    },
                    {
                        "title": "CrewAI v1.0正式版发布",
                        "summary": "CrewAI v1.0新增层级式Agent组织、条件任务流和Human-in-the-Loop审批节点。",
                        "score": 8.0,
                        "url": "https://github.com/crewAIInc/crewAI",
                        "source": "github",
                        "tags": ["Agent", "框架", "开源"],
                    },
                ],
            },
            {
                "title": "AI工具链与基础设施",
                "items": [
                    {
                        "title": "vLLM v0.7推理吞吐量提升2倍",
                        "summary": "vLLM v0.7引入PagedAttention V3和FP8量化，单卡A100可跑70B模型。",
                        "score": 8.5,
                        "url": "https://github.com/vllm-project/vllm/releases/tag/v0.7.0",
                        "source": "github",
                        "tags": ["推理", "基础设施", "开源"],
                    },
                ],
            },
            {
                "title": "AI政策与行业动态",
                "items": [
                    {
                        "title": "欧盟AI法案第二阶段生效",
                        "summary": "覆盖Agent系统、自动驾驶和医疗AI。要求透明性报告和人工监督。违规罚全球营收7%。",
                        "score": 8.2,
                        "url": "https://techcrunch.com/2026/05/24/eu-ai-act-phase-2",
                        "source": "rss",
                        "tags": ["政策", "监管", "欧盟"],
                    },
                ],
            },
        ],
        "key_takeaways": [
            "开源模型与闭源差距缩小至0.3%，Llama-4-R1和DeepSeek-V4成为里程碑",
            "Agent原生能力成为大模型标配，Gemini 3.0和Claude Opus 4.7引领趋势",
            "AI工具链基础设施加速成熟，vLLM/ChromaDB/RAGFlow密集发布大版本",
            "欧盟AI监管正式落地，合规成本将成为AI企业重要考量",
        ],
        "raw_stats": {"fetched": 30, "scored": 30, "passed": 14, "dedup_removed": 2},
        "generated_at": "2026-05-24T08:00:00+00:00",
    },
    {
        "id": "b0000001-0000-0000-0000-000000000002",
        "type": "morning",
        "date": "2026-05-23",
        "language": "zh",
        "tl_dr": [
            "Anthropic Claude Opus 4.6发布，Agent能力显著提升",
            "LangChain发布多Agent协作框架",
            "ChromaDB向量数据库达到十亿级规模",
            "HuggingFace发布Transformers v5.0预览版",
            "中国信通院发布Agent产业白皮书",
        ],
        "sections": [
            {
                "title": "大模型动态",
                "items": [
                    {
                        "title": "Claude Opus 4.6发布",
                        "summary": "Anthropic发布Claude Opus 4.6，Agent能力进一步提升。",
                        "score": 9.0,
                        "url": "https://example.com/claude-4-6",
                        "source": "rss",
                        "tags": ["LLM", "Anthropic"],
                    }
                ],
            }
        ],
        "key_takeaways": ["Agent能力成为大模型核心竞争力"],
        "raw_stats": {"fetched": 28, "scored": 28, "passed": 12},
        "generated_at": "2026-05-23T08:00:00+00:00",
    },
    {
        "id": "b0000001-0000-0000-0000-000000000003",
        "type": "evening",
        "date": "2026-05-23",
        "language": "zh",
        "tl_dr": [
            "Dify v1.5多Agent工作流上线",
            "PromptFlow开源引发LLM工具链讨论",
            "斯坦福AI指数2026发布，中国论文数量领先",
            "Next.js 16内置RAG API",
            "Langfuse v3.0实时成本追踪",
        ],
        "sections": [
            {
                "title": "AI工具链",
                "items": [
                    {
                        "title": "Dify v1.5发布",
                        "summary": "新增多Agent工作流和RAG管道可视化编排。",
                        "score": 8.5,
                        "url": "https://github.com/langgenius/dify",
                        "source": "github",
                        "tags": ["工具", "RAG", "开源"],
                    }
                ],
            }
        ],
        "key_takeaways": ["AI开发工具链日趋成熟，低代码Agent构建成为趋势"],
        "raw_stats": {"fetched": 25, "scored": 25, "passed": 10},
        "generated_at": "2026-05-23T20:00:00+00:00",
    },
]

MOCK_SUBSCRIPTIONS = [
    {"openid": "mock_openid_user_001", "morning_enabled": True, "evening_enabled": True},
    {"openid": "mock_openid_user_002", "morning_enabled": True, "evening_enabled": False},
    {"openid": "mock_openid_user_003", "morning_enabled": False, "evening_enabled": True},
    {"openid": "mock_openid_user_004", "morning_enabled": False, "evening_enabled": False},
    {"openid": "mock_openid_user_005", "morning_enabled": True, "evening_enabled": True},
]


def get_briefings():
    return copy.deepcopy(BRIEFINGS)


def get_subscriptions():
    return copy.deepcopy(MOCK_SUBSCRIPTIONS)


# ── Phase 2 新增假数据 ──────────────────────────────────────────

TAG_CATALOG = [
    {"tag": "LLM", "category": "topic", "label_zh": "大模型", "description": "LLM/ChatGPT/Claude/Gemini等", "sort_order": 1},
    {"tag": "开源", "category": "topic", "label_zh": "开源项目", "description": "开源框架、工具、模型", "sort_order": 2},
    {"tag": "Python", "category": "topic", "label_zh": "Python", "description": "Python生态/AI开发", "sort_order": 3},
    {"tag": "AI安全", "category": "topic", "label_zh": "AI安全", "description": "对齐/红队/鲁棒性", "sort_order": 4},
    {"tag": "Agent", "category": "topic", "label_zh": "智能体", "description": "AI Agent/多Agent协作", "sort_order": 5},
    {"tag": "AI产品", "category": "topic", "label_zh": "AI产品", "description": "AI应用/商业化/SaaS", "sort_order": 6},
    {"tag": "RAG", "category": "topic", "label_zh": "RAG", "description": "检索增强生成", "sort_order": 7},
    {"tag": "多模态", "category": "topic", "label_zh": "多模态", "description": "视觉/语音/视频理解", "sort_order": 8},
    {"tag": "AI编程", "category": "topic", "label_zh": "AI编程", "description": "Copilot/IDE/代码生成", "sort_order": 9},
    {"tag": "AI政策", "category": "topic", "label_zh": "AI政策", "description": "监管/合规/政策/伦理", "sort_order": 10},
    {"tag": "融资", "category": "topic", "label_zh": "融资并购", "description": "AI创投/融资/acquisition", "sort_order": 11},
    {"tag": "基础设施", "category": "topic", "label_zh": "基础设施", "description": "GPU/推理/部署/向量数据库", "sort_order": 12},
]

MOCK_USER_PREFERENCES = {
    "mock_openid_user_001": {"tags": ["LLM", "开源", "Agent"]},
    "mock_openid_user_002": {"tags": ["Python", "AI编程"]},
    "mock_openid_user_003": {"tags": []},  # 无标签，冷启动用户
}

_now = datetime.utcnow()

MOCK_BEHAVIORS = [
    {
        "id": "beh-001",
        "user_openid": "mock_openid_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "item_index": 0,
        "item_title": "Meta开源Llama-4-R1推理增强模型",
        "item_url": "https://github.com/meta-llama/llama4",
        "item_tags": ["LLM", "开源", "推理"],
        "action": "click",
        "created_at": (_now - timedelta(days=1)).isoformat(),
    },
    {
        "id": "beh-002",
        "user_openid": "mock_openid_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "item_index": 3,
        "item_title": "Google Gemini 3.0首次支持Agent原生能力",
        "item_url": "https://blog.google/technology/ai/gemini-3-agent/",
        "item_tags": ["Agent", "Gemini", "多模态"],
        "action": "click",
        "created_at": (_now - timedelta(days=1)).isoformat(),
    },
    {
        "id": "beh-003",
        "user_openid": "mock_openid_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "item_index": 1,
        "item_title": "DeepSeek-V4技术报告解读",
        "item_url": "https://news.ycombinator.com/item?id=40000001",
        "item_tags": ["LLM", "开源", "MoE"],
        "action": "share",
        "created_at": (_now - timedelta(hours=12)).isoformat(),
    },
    {
        "id": "beh-004",
        "user_openid": "mock_openid_user_002",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "item_index": 4,
        "item_title": "CrewAI v1.0正式版发布",
        "item_url": "https://github.com/crewAIInc/crewAI",
        "item_tags": ["Agent", "框架", "开源"],
        "action": "click",
        "created_at": (_now - timedelta(days=2)).isoformat(),
    },
    {
        "id": "beh-005",
        "user_openid": "mock_openid_user_002",
        "briefing_id": "b0000001-0000-0000-0000-000000000002",
        "item_index": 0,
        "item_title": "Claude Opus 4.6发布",
        "item_url": "https://example.com/claude-4-6",
        "item_tags": ["LLM", "Anthropic"],
        "action": "view",
        "created_at": (_now - timedelta(days=3)).isoformat(),
    },
]


def get_tags():
    return copy.deepcopy(TAG_CATALOG)


def get_user_preferences(openid: str) -> dict | None:
    prefs = MOCK_USER_PREFERENCES.get(openid)
    return copy.deepcopy(prefs) if prefs else None


def get_user_behaviors(openid: str) -> list[dict]:
    return [copy.deepcopy(b) for b in MOCK_BEHAVIORS if b["user_openid"] == openid]
