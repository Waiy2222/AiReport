-- ============================================================
-- AI 璧勮��鏃╂姤/鏅氭姤鏅鸿兘浣� 路 绉嶅瓙鏁版嵁
-- 璁╂瘡涓�妯″潡鎷垮埌鍗冲彲鐙�绔嬪紑鍙戯紝涓嶉渶瑕佺瓑鍏朵粬妯″潡瀹屾垚
-- ============================================================

-- 鈹�鈹� raw_items: 30鏉″亣 AI 璧勮��锛堟ā鎷� A 妯″潡鎶撳彇缁撴灉锛屼緵 B 寮�鍙戠敤锛夆攢鈹�鈹�鈹�
INSERT INTO raw_items (id, source, title, url, content, author, published_at, batch_id) VALUES
('a0000001-0000-0000-0000-000000000001', 'github', 'LangChain鍙戝竷v0.3鐗堟湰锛屾柊澧炲�欰gent鍗忎綔鑳藉姏', 'https://github.com/langchain-ai/langchain/releases/tag/v0.3.0', 'LangChain v0.3.0 姝ｅ紡鍙戝竷锛屾柊澧濵ultiAgentCoordinator绫伙紝鏀�鎸佸�氫釜Agent涔嬮棿鐨勬秷鎭�浼犻�掑拰浠诲姟鍒嗛厤銆�', 'langchain-ai', '2026-05-24 02:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000002', 'github', 'Open Source LLM Tool Calling Framework: Gorilla v2.0', 'https://github.com/ShishirPatil/gorilla', 'Gorilla v2.0 鍙戝竷锛屾柊澧炲�笴laude銆丟emini銆丏eepSeek绛夋ā鍨嬬殑tool calling鏀�鎸侊紝鍑嗙‘鐜囨彁鍗囪嚦95%銆�', 'ShishirPatil', '2026-05-24 04:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000003', 'github', 'Ollama Stars绐佺牬10涓囷紝鎴愪负鏈�娴佽�岀殑鏈�鍦癓LM杩愯�屾椂', 'https://github.com/ollama/ollama', 'Ollama鍦℅itHub涓奡tars绐佺牬10涓囷紝鏀�鎸乵acOS/Linux/Windows涓夊钩鍙帮紝鏈�鏂扮増鏈�鏂板�炲�笵eepSeek-V4鐨勬湰鍦拌繍琛屾敮鎸併��', 'ollama', '2026-05-23 18:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000004', 'github', 'AutoGPT鍙戝竷鑷�涓籄gent妗嗘灦v0.6', 'https://github.com/Significant-Gravitas/AutoGPT', 'AutoGPT v0.6 閲嶆瀯浜嗘牳蹇冭皟搴﹀紩鎿庯紝鏀�鎸佸瓙Agent鐨勫姩鎬佸垱寤哄拰閿�姣侊紝鍐呭瓨绠＄悊浼樺寲30%銆�', 'Significant-Gravitas', '2026-05-24 01:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000005', 'github', 'vLLM鍙戝竷v0.7.0锛屾帹鐞嗗悶鍚愰噺鎻愬崌2鍊�', 'https://github.com/vllm-project/vllm/releases/tag/v0.7.0', 'vLLM v0.7.0寮曞叆PagedAttention V3鍜孎P8閲忓寲锛屽崟鍗�A100鍙�璺�70B妯″瀷锛屽悶鍚愰噺鐩歌緝v0.6鎻愬崌2鍊嶃��', 'vllm-project', '2026-05-24 06:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000006', 'github', 'MCP (Model Context Protocol) Python SDK姝ｅ紡鍙戝竷', 'https://github.com/modelcontextprotocol/python-sdk', 'Anthropic寮�婧怣CP鐨凱ython SDK锛屾彁渚涙爣鍑嗗寲鐨凙I妯″瀷涓婁笅鏂囩�＄悊鎺ュ彛锛屾敮鎸佸�歅rovider鍒囨崲銆�', 'modelcontextprotocol', '2026-05-23 14:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000007', 'github', 'ChromaDB鍙戝竷鍚戦噺鏁版嵁搴搗1.0', 'https://github.com/chroma-core/chroma', 'ChromaDB v1.0姝ｅ紡鐗堝彂甯冿紝鏀�鎸佸崄浜跨骇鍚戦噺妫�绱�锛屾柊澧濰NSW绱㈠紩锛屾煡璇㈠欢杩熼檷鑷�5ms銆�', 'chroma-core', '2026-05-24 00:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000008', 'github', 'HuggingFace Transformers v5.0鏋舵瀯閲嶆瀯', 'https://github.com/huggingface/transformers', 'Transformers v5.0鍙戝竷锛岀粺涓�浜哃LM銆佸�氭ā鎬佸拰鎵╂暎妯″瀷鐨凙PI锛屽紩鍏�AutoModelV2鑷�鍔ㄩ�夊瀷鏈哄埗銆�', 'huggingface', '2026-05-23 22:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000009', 'github', 'Meta寮�婧怢lama-4-R1鎺ㄧ悊澧炲己妯″瀷', 'https://github.com/meta-llama/llama4', 'Meta鍙戝竷Llama-4-R1锛屽熀浜庡己鍖栧�︿範鐨勬帹鐞嗗�炲己鐗堟湰锛屽湪MATH鍜孉RC娴嬭瘯涓�杈惧埌GPT-5鍚岀骇姘村钩锛岄噰鐢∕IT璁稿彲璇併��', 'meta-llama', '2026-05-24 03:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000010', 'github', 'Dify鍙戝竷AI搴旂敤鏋勫缓骞冲彴v1.5', 'https://github.com/langgenius/dify', 'Dify v1.5鏂板�炲�欰gent宸ヤ綔娴併�丷AG绠￠亾鍙�瑙嗗寲缂栨帓銆佺煡璇嗗簱澶氭牸寮忔敮鎸侊紙PDF/Word/Notion/缃戦〉锛�', 'langgenius', '2026-05-23 20:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000011', 'hackernews', 'DeepSeek-V4:涓�鍥介�栦釜鍏ㄥ紑婧怣oE澶фā鍨嬬殑鎶�鏈�鎶ュ憡瑙ｈ��', 'https://news.ycombinator.com/item?id=40000001', 'DeepSeek鍙戝竷V4鎶�鏈�鎶ュ憡锛孧oE鏋舵瀯370B鍙傛暟锛岃��缁冩垚鏈�浠�$5M锛屽�氶」鍩哄噯瓒呰繃GPT-4o銆侶N绀惧尯鐑�鐑堣�ㄨ�哄紑婧恦s闂�婧愮殑鏈�鏉ャ��', 'tech_review', '2026-05-24 05:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000012', 'hackernews', 'Anthropic鍙戝竷Claude Opus 4.7锛岀紪绋嬭兘鍔涘ぇ骞呮彁鍗�', 'https://news.ycombinator.com/item?id=40000002', 'Claude Opus 4.7鍦⊿WE-Bench Verified涓婅揪鍒�85%鍑嗙‘鐜囷紝瓒呰秺鎵�鏈夌珵鍝併�傛敮鎸�200K涓婁笅鏂囩獥鍙ｃ��', 'ai_explorer', '2026-05-24 07:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000013', 'hackernews', '涓轰粈涔堟垜浠�鍐冲畾灏嗘墍鏈夊井鏈嶅姟杩佺Щ鍒板崟浣撳簲鐢�', 'https://news.ycombinator.com/item?id=40000003', '涓�浣岰TO鍒嗕韩灏咥I鍒涗笟鍏�鍙哥殑寰�鏈嶅姟鏋舵瀯杩佺Щ鍒板崟浣撶殑缁忛獙锛屽紩鍙戜簡鍏充簬杩囨棭浼樺寲涓庡伐绋嬪�嶆潅搴︾殑璁ㄨ�恒��', 'cto_startup', '2026-05-23 16:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000014', 'hackernews', 'OpenAI琚�鏇濇�ｅ湪寮�鍙戝叏鏂版帹鐞嗘灦鏋�"Strawberry"', 'https://news.ycombinator.com/item?id=40000004', '鎹甌he Information鎶ラ亾锛孫penAI鍐呴儴姝ｅ湪寮�鍙戜唬鍙稴trawberry鐨勬柊鍨嬫帹鐞嗘灦鏋勶紝鍙�鑳藉湪鏁板�﹀拰缂栫▼鏂归潰鏈夎川鐨勯�炶穬銆�', 'insider_news', '2026-05-24 08:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000015', 'hackernews', 'Show HN:鎴戝仛浜嗕釜寮�婧怉I浠ｇ爜瀹℃煡宸ュ叿锛岀敤鏈�鍦癓LM淇濇姢闅愮��', 'https://news.ycombinator.com/item?id=40000005', '浣滆�呭垎浜�鍩轰簬Ollama+Llama-4鐨勫紑婧愪唬鐮佸�℃煡宸ュ叿锛屽畬鍏ㄦ湰鍦拌繍琛岋紝鏀�鎸丟itHub/GitLab闆嗘垚锛屽凡鏈�500+Stars銆�', 'indie_dev', '2026-05-23 21:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000016', 'rss', 'Google DeepMind鍙戝竷Gemini 3.0锛岄�栨�℃敮鎸丄gent鍘熺敓鑳藉姏', 'https://blog.google/technology/ai/gemini-3-agent/', 'Gemini 3.0寮曞叆Agent API锛屾敮鎸佸�氭�ュ伐鍏疯皟鐢ㄣ�佹祻瑙堝櫒鑷�鍔ㄥ寲鍜屼唬鐮佹墽琛屻�傚湪MMLU-Pro涓婅揪鍒�92%銆�', 'Google AI Blog', '2026-05-24 00:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000017', 'rss', '涓�鍥戒俊閫氶櫌鍙戝竷銆�2026骞碅I Agent浜т笟鐧界毊涔︺��', 'https://www.caict.ac.cn/ai-agent-2026', '鐧界毊涔︽寚鍑�2026骞村叏鐞傾gent甯傚満瑙勬ā绐佺牬200浜跨編鍏冿紝涓�鍥戒紒涓氱骇Agent搴旂敤澧為暱鏈�蹇�锛屾櫤鑳藉�㈡湇鍜屼唬鐮佸姪鎵嬫槸涓ゅぇ绐佺牬鍙ｃ��', '涓�鍥戒俊閫氶櫌', '2026-05-24 06:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000018', 'rss', 'MIT鐮旂┒鍥㈤槦鎻愬嚭鏂扮殑Agent璇勪及妗嗘灦AgentBench V2', 'https://news.mit.edu/2026/agent-bench-v2', 'MIT CSAIL鍙戝竷AgentBench V2锛岃�嗙洊200+鐪熷疄浠诲姟鍦烘櫙锛屽寘鎷�浠ｇ爜銆佺綉缁溿�佹枃浠舵搷浣滅瓑锛屾垚涓篈gent鑳藉姏璇勪及鏂版爣鍑嗐��', 'MIT News', '2026-05-23 15:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000019', 'rss', 'OpenAI寮�婧怗PT-OSS锛氫竴涓�鍙�鍦ㄦ秷璐圭骇纭�浠朵笂杩愯�岀殑鎺ㄧ悊妯″瀷', 'https://openai.com/blog/gpt-oss', 'OpenAI鎰忓�栧紑婧怗PT-OSS锛�7B鍙傛暟锛屽彲鍦∕acBook涓婅繍琛岋紝鍦ㄦ暟瀛﹀拰浠ｇ爜鏂归潰鎺ヨ繎GPT-5-mini姘村钩銆傜ぞ鍖哄弽搴斾袱鏋佸寲銆�', 'OpenAI Blog', '2026-05-24 04:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000020', 'rss', 'Next.js 16鍙戝竷锛欰I-first妗嗘灦锛屽唴缃甊AG API', 'https://nextjs.org/blog/next-16', 'Vercel鍙戝竷Next.js 16锛岄�栨�″唴缃甊AG API鍜孉I Agent璺�鐢憋紝鏀�鎸丼treaming SSR涓嶦dge Runtime鐨勬繁搴﹁瀺鍚堛��', 'Vercel Blog', '2026-05-23 19:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000021', 'github', 'CrewAI澶欰gent妗嗘灦鍙戝竷v1.0姝ｅ紡鐗�', 'https://github.com/crewAIInc/crewAI', 'CrewAI v1.0鍙戝竷锛屾柊澧炲眰绾у紡Agent缁勭粐銆佹潯浠朵换鍔℃祦鍜孒uman-in-the-Loop瀹℃壒鑺傜偣锛屼紒涓氱骇鐗规�у畬鍠勩��', 'crewAIInc', '2026-05-24 05:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000022', 'hackernews', '寰�杞�寮�婧怭romptFlow锛歀LM搴旂敤鐨勫彲瑙嗗寲寮�鍙戝伐鍏�', 'https://news.ycombinator.com/item?id=40000006', '寰�杞�灏嗗唴閮≒romptFlow宸ュ叿寮�婧愶紝鏀�鎸佸彲瑙嗗寲缂栨帓LLM閾俱�佽瘎浼板拰閮ㄧ讲銆傜ぞ鍖哄�规瘮LangChain鍜孌ify鐨勬柟妗堜紭鍔ｃ��', 'ms_dev', '2026-05-23 23:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000023', 'rss', '鏂�鍧︾�忓彂甯傾I鎸囨暟2026骞村害鎶ュ憡', 'https://aiindex.stanford.edu/report/2026/', '鏂�鍧︾�廐AI鍙戝竷2026骞碅I鎸囨暟鎶ュ憡锛氫腑鍥藉湪AI璁烘枃鏁伴噺鍜屼笓鍒╂柟闈㈤�嗗厛锛岀編鍥藉湪妯″瀷鑳藉姏鍜屾姇璧勬柟闈㈤�嗗厛銆傚紑婧愭ā鍨嬩笌闂�婧愭ā鍨嬪樊璺濈缉灏忚嚦0.3%銆�', 'Stanford HAI', '2026-05-24 01:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000024', 'github', 'RAGFlow寮�婧怰AG寮曟搸鍙戝竷v2.0', 'https://github.com/infiniflow/ragflow', 'RAGFlow v2.0鏂板�濭raph RAG銆佸�氭ā鎬佹��绱㈠拰Agentic RAG鑳藉姏锛屾敮鎸侀潪缁撴瀯鍖栨枃妗ｆ繁搴︾悊瑙ｏ紝浼佷笟绾ч儴缃叉柟妗堝畬鍠勩��', 'infiniflow', '2026-05-23 17:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000025', 'hackernews', 'AI缂栫▼鍔╂墜甯傚満鏍煎眬鍒嗘瀽涓�2026瓒嬪娍棰勬祴', 'https://news.ycombinator.com/item?id=40000007', '涓�浣嶈祫娣卞紑鍙戣�呭�笹itHub Copilot銆丆ursor銆丆laude Code銆乄indsurf绛�7娆続I缂栫▼宸ュ叿杩涜�屾繁搴︽í璇勶紝寮曞彂绀惧尯瀵笽DE鏈�鏉ョ殑璁ㄨ�恒��', 'dev_analyst', '2026-05-24 06:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000026', 'rss', '闃块噷閫氫箟鍗冮棶鍙戝竷Qwen-3-Max锛屼腑鏂囪兘鍔涘叏闈㈤�嗗厛', 'https://tongyi.aliyun.com/blog/qwen-3-max', '閫氫箟鍗冮棶Qwen-3-Max鍙戝竷锛屽湪C-Eval銆丆MMLU绛変腑鏂囧熀鍑嗘祴璇曚腑鍏ㄩ潰棰嗗厛锛屾敮鎸�100涓囧瓧闀夸笂涓嬫枃锛孉PI浠锋牸浠呬负GPT-5鐨�1/10銆�', '闃块噷浜�', '2026-05-24 02:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000027', 'github', 'Langfuse鍙戝竷LLM鍙�瑙傛祴鎬у钩鍙皏3.0', 'https://github.com/langfuse/langfuse', 'Langfuse v3.0鏀�鎸佸疄鏃禩oken鎴愭湰杩借釜銆丄gent璋冪敤閾惧彲瑙嗗寲銆佽嚜鍔ㄥ寲璇勪及鍜屽憡璀︼紝鏀�鎸佽嚜閮ㄧ讲鍜屼簯鏈嶅姟涓ょ�嶆ā寮忋��', 'langfuse', '2026-05-23 13:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000028', 'hackernews', 'YC 2026澶忓�ｆ壒娆★細AI鍒濆垱鍏�鍙稿崰姣旈�栨�¤秴杩�80%', 'https://news.ycombinator.com/item?id=40000008', 'Y Combinator 2026骞村�忓�ｆ壒娆″叡鏈�230瀹跺垵鍒涘叕鍙革紝鍏朵腑AI鐩稿叧鍗�82%銆備富瑕佹槸AI Agent宸ュ叿銆佸瀭鐩磋�屼笟AI搴旂敤鍜孉I鍩虹��璁炬柦銆�', 'yc_observer', '2026-05-24 07:30:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000029', 'rss', '娆х洘AI娉曟�堢��浜岄樁娈垫�ｅ紡瀹炴柦锛氶珮椋庨櫓AI绯荤粺闇�寮哄埗澶囨��', 'https://techcrunch.com/2026/05/24/eu-ai-act-phase-2', '娆х洘AI娉曟�堢��浜岄樁娈电敓鏁堬紝瑕嗙洊Agent绯荤粺銆佽嚜鍔ㄩ┚椹跺拰鍖荤枟AI銆傝�佹眰閫忔槑鎬ф姤鍛娿�佷汉宸ョ洃鐫ｆ満鍒跺拰椋庨櫓璇勪及銆傝繚瑙勬渶楂樼綒鍏ㄧ悆钀ユ敹鐨�7%銆�', 'TechCrunch', '2026-05-24 08:00:00+00', 'seed-batch-001'),
('a0000001-0000-0000-0000-000000000030', 'github', 'PaddlePaddle鍙戝竷椋炴〃3.0锛氫腑鏂嘇I寮�鍙戣�呯殑棣栭�夋�嗘灦', 'https://github.com/PaddlePaddle/Paddle', '鐧惧害椋炴〃3.0鍙戝竷锛屽叏闈㈡敮鎸佸ぇ妯″瀷璁�缁冨拰鎺ㄧ悊锛屾柊澧濧utoParallel鍒嗗竷寮忚��缁冿紝涓�鏂嘚LP棰勮��缁冩ā鍨嬪簱鎵╁厖鑷�500+銆�', 'PaddlePaddle', '2026-05-24 00:00:00+00', 'seed-batch-001');

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
