"""Re-insert clean UTF-8 seed data into PostgreSQL."""
import asyncio
import json
import uuid
from datetime import datetime, timezone, date

import asyncpg


async def main():
    pool = await asyncpg.create_pool(
        "postgresql://postgres:postgres@localhost:5432/ai_news",
        min_size=1, max_size=4,
    )

    await pool.execute("DELETE FROM publish_log")
    await pool.execute("DELETE FROM raw_items")
    await pool.execute("DELETE FROM briefings")

    sources = ["github", "hackernews", "rss", "reddit", "rss", "github",
               "hackernews", "rss", "github", "reddit"]
    titles = [
        "LangChain发布v0.6版本，新增多Agent协作能力",
        "开源LLM工具调用框架Gorilla v2.0发布",
        "Ollama Stars突破10万，成为最流行的本地LLM运行时",
        "OpenAI开源GPT-OSS 7B推理模型",
        "Claude Code新增多模型切换支持",
        "DeepSeek-V4技术报告引发全球关注",
        "Meta开源Llama-4-R1推理增强模型",
        "Google DeepMind发布Gemini 3.0",
        "Anthropic发布Claude Opus 4.7",
        "YC 2026夏季批次AI初创占比82%",
        "vLLM v0.7推理吞吐量提升2倍",
        "CrewAI v1.0和AutoGPT v0.6同日发布",
        "HuggingFace Transformers v5.0统一多模态API",
        "欧盟AI法案第二阶段生效",
        "微软发布Phi-4-Multimodal多模态小模型",
        "Apple开源MLX框架支持分布式训练",
        "Stability AI发布Stable Diffusion 4.0",
        "字节跳动开源即梦AI视频生成模型",
        "百度文心一言5.0全面免费开放",
        "阿里通义千问3.0登顶C-Eval榜首",
        "智谱AI发布GLM-5开源模型",
        "Mistral AI发布Mistral Large 3",
        "Cohere发布Command R+企业级模型",
        "Perplexity AI估值突破200亿美元",
        "Cursor IDE新增Agent模式",
        "Replit发布AI原生开发环境",
        "Notion AI新增知识库问答功能",
        "Figma AI支持设计稿一键生成代码",
        "Cloudflare发布Workers AI边缘推理",
        "NVIDIA发布B300 GPU推理性能翻倍",
    ]
    contents = [
        "新增MultiAgentCoordinator类，支持多Agent消息传递和任务分配。",
        "新增对Claude、Gemini、DeepSeek等模型的tool calling支持。",
        "支持macOS/Linux/Windows三平台，新增DeepSeek-V4本地运行支持。",
        "可在消费级硬件运行，采用MoE架构，MIT许可证开源发布。",
        "支持Claude Opus/Sonnet/Haiku之间无缝切换。",
        "MoE架构370B参数开源，训练成本仅500万美元。",
        "MIT许可证，多项基准达GPT-5同级水平。",
        "首次原生支持Agent API，可直接调用工具和代码执行。",
        "SWE-Bench Verified准确率85%。",
        "Agent工具和垂直应用成为热门赛道。",
        "FP8量化支持70B模型单卡部署。",
        "多Agent框架竞争白热化。",
        "统一文本、图像、音频模型的加载接口。",
        "高风险AI系统需强制备案。",
        "支持图像、语音、视频多模态输入，参数量仅7B。",
        "支持在Mac和iOS设备上进行分布式训练。",
        "图像生成质量大幅提升，新增视频生成能力。",
        "支持文生视频和图生视频。",
        "全面免费开放API调用，支持超长上下文。",
        "在中文理解和生成方面表现优异，支持128K上下文。",
        "在多项中文基准测试中表现优异。",
        "在推理和代码生成方面表现优异。",
        "专为企业级应用优化，支持私有部署。",
        "AI搜索引擎月活用户突破5000万。",
        "AI编程工具新增自主Agent能力。",
        "基于浏览器的AI开发环境。",
        "支持上传文档自动生成知识库。",
        "AI自动生成前端代码，支持多种框架。",
        "在全球300+数据中心部署AI推理能力。",
        "专为大模型推理优化，能效比提升3倍。",
    ]
    authors = [
        "langchain-ai", "ShishirPatil", "ollama", "openai", "anthropic",
        "deepseek", "meta", "google", "anthropic", "yc",
        "vllm", "crewai", "huggingface", "eu", "microsoft",
        "apple", "stability", "bytedance", "baidu", "alibaba",
        "zhipu", "mistral", "cohere", "perplexity", "cursor",
        "replit", "notion", "figma", "cloudflare", "nvidia",
    ]

    batch_id = uuid.uuid4()
    for i in range(30):
        await pool.execute(
            """INSERT INTO raw_items (source, title, url, content, author, published_at, batch_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            sources[i % len(sources)],
            titles[i],
            f"https://example.com/news/{i+1}",
            contents[i],
            authors[i],
            datetime(2026, 5, 24, 2 + (i % 22), 0, 0, tzinfo=timezone.utc),
            batch_id,
        )
    print(f"Inserted 30 raw_items")

    briefing_data = [
        {
            "type": "morning", "date": "2026-05-24",
            "tl_dr": [
                "DeepSeek-V4技术报告引发全球关注，MoE架构370B参数开源",
                "Meta开源Llama-4-R1推理增强模型，MIT许可证",
                "Anthropic发布Claude Opus 4.7，SWE-Bench准确率85%",
                "OpenAI开源GPT-OSS 7B推理模型，可在消费级硬件运行",
                "Google DeepMind发布Gemini 3.0，首次原生支持Agent API",
                "欧盟AI法案第二阶段生效，高风险AI系统需强制备案",
                "YC 2026夏季批次AI初创占比82%，Agent工具成热点",
                "vLLM v0.7推理吞吐量提升2倍，FP8量化支持70B单卡部署",
                "CrewAI v1.0和AutoGPT v0.6同日发布，Agent框架竞争白热化",
                "HuggingFace Transformers v5.0统一多模态API架构",
            ],
            "sections": [
                {
                    "title": "大模型发布与更新",
                    "items": [
                        {"title": "DeepSeek-V4技术报告发布", "summary": "MoE架构370B参数开源模型，训练成本仅500万美元，多项基准测试达到GPT-5同级水平。",
                         "score": 9.5, "source": "github", "url": "https://example.com/news/6", "tags": ["DeepSeek", "开源", "MoE"]},
                        {"title": "Meta开源Llama-4-R1", "summary": "推理增强模型采用MIT许可证，在数学、代码和多语言推理方面表现优异。",
                         "score": 9.3, "source": "github", "url": "https://example.com/news/7", "tags": ["Meta", "Llama", "开源"]},
                        {"title": "Anthropic发布Claude Opus 4.7", "summary": "SWE-Bench Verified准确率达85%，代码生成和调试表现突出。",
                         "score": 9.0, "source": "hackernews", "url": "https://example.com/news/9", "tags": ["Anthropic", "Claude"]},
                    ],
                },
                {
                    "title": "开源生态与工具",
                    "items": [
                        {"title": "OpenAI开源GPT-OSS 7B", "summary": "可在消费级硬件运行的推理模型，MIT许可证，适合本地部署和学术研究。",
                         "score": 8.8, "source": "github", "url": "https://example.com/news/4", "tags": ["OpenAI", "开源"]},
                        {"title": "vLLM v0.7发布", "summary": "推理吞吐量提升2倍，FP8量化支持70B模型单卡部署。",
                         "score": 8.2, "source": "github", "url": "https://example.com/news/11", "tags": ["vLLM", "推理"]},
                    ],
                },
            ],
            "key_takeaways": [
                "开源大模型进入爆发期：DeepSeek-V4、Llama-4-R1、GPT-OSS三款重量级开源模型同时发布",
                "Agent能力成为差异化竞争焦点：Gemini 3.0、Claude Opus均强化Agent能力",
                "AI合规化加速：欧盟AI法案生效，全球AI治理进入新阶段",
            ],
        },
        {
            "type": "morning", "date": "2026-05-23",
            "tl_dr": [
                "Google DeepMind发布Gemini 3.0，首次原生支持Agent API",
                "微软发布Phi-4-Multimodal多模态小模型",
                "Apple开源MLX框架支持分布式训练",
                "Stability AI发布Stable Diffusion 4.0",
            ],
            "sections": [
                {
                    "title": "模型发布",
                    "items": [
                        {"title": "Gemini 3.0发布", "summary": "首次原生支持Agent API，多模态能力大幅提升。",
                         "score": 9.2, "source": "hackernews", "url": "https://example.com/news/8", "tags": ["Google", "Gemini"]},
                        {"title": "Phi-4-Multimodal", "summary": "微软发布多模态小模型，支持图像、语音、视频输入，参数量仅7B。",
                         "score": 8.5, "source": "github", "url": "https://example.com/news/15", "tags": ["Microsoft", "Phi"]},
                    ],
                },
            ],
            "key_takeaways": ["多模态和Agent能力成为大模型标配", "小模型在特定场景表现不输大模型"],
        },
        {
            "type": "evening", "date": "2026-05-23",
            "tl_dr": [
                "百度文心一言5.0全面免费开放，阿里通义千问3.0登顶C-Eval",
                "智谱AI发布GLM-5开源模型，Mistral发布Large 3",
                "Cursor IDE新增Agent模式，Replit发布AI原生开发环境",
                "NVIDIA发布B300 GPU推理性能翻倍",
            ],
            "sections": [
                {
                    "title": "国内大模型动态",
                    "items": [
                        {"title": "文心一言5.0全面免费", "summary": "百度宣布文心一言5.0全面免费开放API调用。",
                         "score": 8.8, "source": "rss", "url": "https://example.com/news/19", "tags": ["百度", "文心一言"]},
                        {"title": "通义千问3.0登顶C-Eval", "summary": "阿里通义千问3.0在中文理解和生成方面表现优异。",
                         "score": 8.7, "source": "rss", "url": "https://example.com/news/20", "tags": ["阿里", "通义千问"]},
                        {"title": "GLM-5开源发布", "summary": "智谱AI发布GLM-5开源模型，中文基准测试表现优异。",
                         "score": 8.5, "source": "github", "url": "https://example.com/news/21", "tags": ["智谱AI", "GLM"]},
                    ],
                },
                {
                    "title": "开发工具与硬件",
                    "items": [
                        {"title": "Cursor IDE新增Agent模式", "summary": "AI编程工具新增自主Agent能力。",
                         "score": 8.3, "source": "hackernews", "url": "https://example.com/news/25", "tags": ["Cursor", "Agent"]},
                        {"title": "NVIDIA B300 GPU发布", "summary": "专为大模型推理优化，能效比提升3倍。",
                         "score": 8.0, "source": "rss", "url": "https://example.com/news/30", "tags": ["NVIDIA", "GPU"]},
                    ],
                },
            ],
            "key_takeaways": ["国内大模型厂商进入全面竞争阶段", "AI开发工具进入Agent时代，自主编程成为标配"],
        },
    ]

    for b in briefing_data:
        await pool.execute(
            "INSERT INTO briefings (type, date, tl_dr, sections, key_takeaways) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb)",
            b["type"],
            date.fromisoformat(b["date"]),
            json.dumps(b["tl_dr"], ensure_ascii=False),
            json.dumps(b["sections"], ensure_ascii=False),
            json.dumps(b["key_takeaways"], ensure_ascii=False),
        )
    print("Inserted 3 briefings")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
