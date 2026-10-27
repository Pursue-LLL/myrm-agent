"""The freshness trigger holds back answers that need outside data, and leaves every other request alone.

The prompts are written by hand, by the author of the rule, in six batches. The first shaped the rule, the second
and third shaped its word lists, the fourth was written after those were frozen, the fifth shaped the short-question
branch (its false triggers decided the advice exclusion), and the sixth was written after that branch was frozen.
Each prompt is labeled by what the request needs, not by what the rule says. They are a regression net, not an
accuracy estimate: the negatives mostly contain a time or topic word on purpose, every prompt is a short sentence,
and nothing here says how often real traffic does.

On these 77 requests that need outside data and 77 that need nothing, the word list the rule replaced (any one of
"latest/today/current/live/news/price/stock/..." and their Chinese forms, unless a code word was present) missed 39
and held 33 of the second kind. This rule misses 5 and holds 4; ``KNOWN_MISSES`` and ``KNOWN_FALSE_TRIGGERS`` list
those, strictly, so a change that fixes one has to move it out of the list.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
    build_external_evidence_reason,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.freshness import demands_external_evidence

NEEDS_FRESH_DATA: tuple[str, ...] = (
    "今天最新的 AI 新闻是什么？",
    "现在比特币的价格是多少？",
    "帮我查一下英伟达最新的股价和行情",
    "北京明天的天气怎么样？",
    "目前美元兑人民币的汇率是多少",
    "OpenAI 最近发布了什么新模型？",
    "Python 最新的稳定版本是哪个？",
    "昨晚 NBA 比赛的比分是多少",
    "帮我搜索一下近期关于固态电池的报道",
    "当前最火的开源 Agent 项目有哪些，附上链接",
    "What's the latest iPhone model and its price?",
    "What is the current weather in Tokyo?",
    "Any news about the EU AI Act today?",
    "What's Tesla's stock price right now?",
    "Search the web for recent reviews of the Framework Laptop 16 and give sources",
    "What is the latest version of React and what changed in it?",
    "Is GitHub having an outage right now?",
    "Give me today's top Hacker News stories",
    "What's the live score of the Lakers game?",
    "帮我看看 DeepSeek 这两天有什么新动态",
    "美股今天收盘了吗，纳指涨了多少",
    "请问苹果最新发布会推出了哪些产品？",
    "What's the weather like in Berlin this weekend?",
    "现在 ETH 多少钱？",
    "Show me the current exchange rate between EUR and JPY",
    "Look up recent news on the Fed rate decision",
    "请联网查询今天的油价",
    "What are the top trending repos on GitHub today?",
    "请帮我查一下今天的黄金价格",
    "What's the newest version of Node.js?",
    "苹果公司现在的市值是多少？",
    "Give me a summary of this week's tech news",
    "2026 年世界杯最新赛程出来了吗",
    "联网搜一下最近的 Rust 异步生态进展",
    "How is the Nasdaq doing right now?",
    "帮我查一下最近一周特斯拉的股价走势",
    "今天的头条新闻有哪些？",
    "Find the most recent research on mRNA vaccines and cite the sources",
    "What's the current gas price in California?",
    "国内最新的大模型榜单是什么？",
    "Give me the live score for tonight's Warriors game",
    "Who won the match last night?",
    "Which team leads the Premier League table right now?",
    "本周有哪些新上映的电影？",
    "Is the Shanghai metro running normally today?",
    "What time does the sun set in Paris today?",
    "What's happening in the Middle East today?",
    "小米 SU7 现在的售价是多少？",
    "What's the weather like in Berlin today?",
    "Did the Fed change interest rates this week?",
    "今天北京限行尾号是多少？",
    "苹果现在的股价是多少？",
    "Is GitHub down right now?",
    "What did the president say in tonight's speech?",
    "昨晚欧冠谁赢了？",
    "Are flights from Heathrow delayed today?",
    "这周末上海有什么展览？",
    "What's the score of the Lakers game tonight?",
    "Is the Golden Gate Bridge closed right now?",
    "Who is leading the polls today?",
    "What is Bitcoin trading at today?",
    "Are there any train strikes in France this week?",
    "Has OpenAI announced anything new today?",
    "今天上海的 PM2.5 是多少？",
    "现在美元兑人民币汇率是多少？",
    "昨晚的 NBA 比赛结果怎么样？",
    "这周有哪些大模型新发布？",
    "苹果最新发布会讲了什么？",
    "现在北京堵车严重吗？",
    "今天高雄會下雨嗎？",
    "現在台積電股價多少？",
    "這週末台北有什麼活動？",
)

NEEDS_NOTHING_EXTERNAL: tuple[str, ...] = (
    "帮我写一个计算股票价格移动平均线的 Python 函数",
    "解释一下什么是实时操作系统",
    "把这段话翻译成英文：今天天气真好",
    "我当前的想法是先把方案想清楚再动手，你觉得这个思路如何？",
    "今天心情不好，给我讲个笑话",
    "价格弹性的定义是什么？举个例子",
    "请帮我润色这封邮件，明天要发给客户",
    "帮我分析一下这个 CSV 里最新一周的销量变化",
    "我们今天来复习一下线性代数的基础概念",
    "什么是新闻学中的倒金字塔结构？",
    "Explain how live migration works in virtual machines",
    "Write a SQL query that returns the current month's orders from my orders table",
    'What does "stock" mean in "stock photo"?',
    "Summarize the text below in two sentences",
    "Explain price elasticity of demand with an example",
    "Rename the variable current_user to active_user across the repo",
    "How should I live-stream my game with OBS?",
    "I'm feeling stuck today, can you help me brainstorm project names?",
    "What's the difference between a stock and a bond?",
    "Proofread this paragraph for grammar mistakes.",
    "帮我把这段 Python 代码改成异步的，现在是同步写法",
    "解释一下 TCP 三次握手的过程",
    "请用现在完成时造三个句子",
    "Why did the Roman Empire fall?",
    "给我一份今天的学习计划模板",
    "What is the time complexity of quicksort?",
    "Create a weekly meal plan for a vegetarian, current weight 70kg",
    "写一篇关于股票投资风险的科普文章",
    "Help me write a product release announcement for our app",
    "这个函数的最新参数是什么意思？",
    "How do stock options vest over four years?",
    "帮我把这个 SQL 优化一下，现在查询要跑 30 秒",
    "What is a stock ticker symbol?",
    "给我讲讲牛顿第二定律",
    "Please translate this contract clause into plain English",
    "帮我写一份新闻稿，介绍我们公司的新产品发布",
    "Recommend a few books about live performance and stage design",
    "我最近在学吉他，有什么练习建议？",
    "How do I structure a README for my open-source project?",
    "当前文件夹里有哪些文件？",
    "现在请你扮演一位面试官，我来回答",
    "帮我写一个爬虫，抓取新闻网站首页标题",
    "What's the best way to learn Spanish quickly?",
    "给我解释一下什么是市盈率",
    "Convert 100 USD to EUR using a fixed rate of 0.92",
    "我今天要去面试，帮我准备几个常见问题",
    "Draft a press release announcing our new office opening",
    "这周的周报我写好了，帮我检查一下语法",
    "Explain the live/dead variable analysis in compilers",
    "Explain the difference between a mutex and a semaphore",
    "How do I schedule a cron job to run every day at 9am?",
    "今天我想复习线性代数，帮我列个学习计划",
    "Write a short poem about this morning's sunrise.",
    "What does 'currently' mean in a present continuous sentence?",
    "What's the difference between a list and a tuple in Python?",
    "Can you rewrite this paragraph so it sounds more formal? I need it today.",
    "解释一下什么是通货膨胀",
    "What should I cook for dinner tonight if I only have rice and eggs?",
    "我现在应该先学 Rust 还是先学 Go？",
    "Explain how HTTP caching works.",
    "I'm feeling stressed today, any tips to relax?",
    "Can you proofread this email? I have to send it today.",
    "What should I name my new puppy?",
    "Write a function that returns today's date in ISO format.",
    "What's the difference between affect and effect?",
    "今天我想学点 Python，有什么入门建议吗？",
    "帮我把这段话翻译成英文，今天要交。",
    "什么是量子纠缠？",
    "我今天应该先复习数学还是英语？",
    "解释一下什么是哈希表",
    "今天想學吉他，有什麼入門建議嗎？",
    "請幫我把這段文字改寫得更正式",
    "什麼是機器學習？",
)

KNOWN_MISSES: tuple[str, ...] = (
    "Can you check if the Python 3.14 release date has been announced?",
    "最近有哪些值得关注的 AI 论文？",
    "Has the new MacBook been released yet?",
    "明天上海会下雨吗？",
    "How much is a Tesla Model Y at the moment?",
)

KNOWN_FALSE_TRIGGERS: tuple[str, ...] = (
    "今天是周几？怎么用 Python 打印当前日期？",
    'Translate "the latest news" into French',
    "现在我有三个苹果，吃了一个，还剩几个？",
    "现在有 5 个人，每人分 2 块饼干，一共需要多少块？",
)


@pytest.mark.parametrize("request_text", NEEDS_FRESH_DATA)
def test_request_for_fresh_data_is_detected(request_text: str) -> None:
    assert demands_external_evidence(request_text)


@pytest.mark.parametrize("request_text", NEEDS_NOTHING_EXTERNAL)
def test_request_needing_nothing_external_is_left_alone(request_text: str) -> None:
    assert not demands_external_evidence(request_text)


@pytest.mark.parametrize("request_text", KNOWN_MISSES)
@pytest.mark.xfail(strict=True, reason="the time is implied by the question or the topic word is not in the lists")
def test_known_miss(request_text: str) -> None:
    assert demands_external_evidence(request_text)


@pytest.mark.parametrize("request_text", KNOWN_FALSE_TRIGGERS)
@pytest.mark.xfail(strict=True, reason="a quoted phrase is indistinguishable from a request for it")
def test_known_false_trigger(request_text: str) -> None:
    assert not demands_external_evidence(request_text)


class TestExplicitLookup:
    """Asking for the web or for sources outranks every exemption."""

    @pytest.mark.parametrize(
        "request_text",
        [
            "分析一下最新的代码，并联网搜索官方文档的最新说明",
            "Rewrite the latest changelog after checking the website",
            "Search online for today's news and translate it into English",
            "Search the web for reviews and give sources",
        ],
    )
    def test_lookup_ask_lifts_the_own_work_and_text_exemptions(self, request_text: str) -> None:
        assert demands_external_evidence(request_text)

    @pytest.mark.parametrize(
        "request_text",
        ["分析最新改动的代码逻辑", "Summarize the latest commit in this repo", "翻译一下：今天天气真好"],
    )
    def test_own_work_and_text_requests_without_a_lookup_ask_are_left_alone(self, request_text: str) -> None:
        assert not demands_external_evidence(request_text)


class TestMatching:
    def test_case_is_ignored(self) -> None:
        assert demands_external_evidence("LATEST NEWS ABOUT THE FED")

    def test_ascii_words_match_whole_words_only(self) -> None:
        assert not demands_external_evidence("The stockroom is closed today")
        assert not demands_external_evidence("rename current_user to active_user in the repo")


class TestGuardReason:
    """The gate asks for evidence only when the trigger fires and the run has none."""

    def test_reason_names_the_request_when_it_needs_fresh_data(self) -> None:
        reason = build_external_evidence_reason(messages=[HumanMessage("今天最新的 AI 新闻是什么？")], records=[])
        assert reason is not None
        assert "今天最新的 AI 新闻是什么？" in reason

    def test_no_reason_for_a_request_that_needs_nothing_external(self) -> None:
        assert build_external_evidence_reason(messages=[HumanMessage("今天心情不好，给我讲个笑话")], records=[]) is None


class TestQuestionAboutTheMoment:
    """A short question about today or right now is a lookup; pasted material and requests for advice are not."""

    @pytest.mark.parametrize(
        "request_text",
        [
            pytest.param(
                "The parties agree that, as of today, the supplier shall deliver the goods within thirty days. " * 8
                + "\nIs clause 3 enforceable if the buyer pays late?",
                id="contract",
            ),
            pytest.param(
                "def f(x):\n    return x.today()\n" * 10 + "\nWhy does this raise an error?", id="code-listing"
            ),
            pytest.param(
                "今天的会议纪要如下：" + "我们讨论了预算和排期，决定下周开始。" * 20 + "\n这份纪要里有哪些风险？",
                id="meeting-minutes",
            ),
        ],
    )
    def test_pasted_material_with_a_question_is_left_alone(self, request_text: str) -> None:
        assert len(request_text) > 200
        assert not demands_external_evidence(request_text)

    @pytest.mark.parametrize(
        "request_text",
        [
            "Should I bring an umbrella tomorrow or today?",
            "What should I cook tonight?",
            "我今天应该先复习数学还是英语？",
        ],
    )
    def test_a_request_for_advice_is_left_alone(self, request_text: str) -> None:
        assert not demands_external_evidence(request_text)

    def test_a_statement_about_today_is_left_alone(self) -> None:
        assert not demands_external_evidence("It rained a lot today and the match was cancelled.")


TRADITIONAL_CHINESE: tuple[tuple[str, str, bool], ...] = (
    ("现在比特币的价格是多少？", "現在比特幣的價格是多少？", True),
    ("北京明天的天气怎么样？", "北京明天的天氣怎麼樣？", True),
    ("目前美元兑人民币的汇率是多少", "目前美元兌人民幣的匯率是多少", True),
    ("请联网查询今天的油价", "請聯網查詢今天的油價", True),
    ("美股今天收盘了吗，纳指涨了多少", "美股今天收盤了嗎，納指漲了多少", True),
    ("今天台北天气如何？", "今天台北天氣如何？", True),
    ("把这段话翻译成英文：今天天气真好", "把這段話翻譯成英文：今天天氣真好", False),
    ("请帮我润色这封邮件，明天要发给客户", "請幫我潤色這封郵件，明天要發給客戶", False),
    ("帮我分析一下这个 CSV 里最新一周的销量变化", "幫我分析一下這個 CSV 裡最新一週的銷量變化", False),
    ("解释一下什么是实时操作系统", "解釋一下什麼是實時作業系統", False),
)


@pytest.mark.parametrize(("simplified", "traditional", "needs_fresh_data"), TRADITIONAL_CHINESE)
def test_traditional_chinese_is_judged_as_its_simplified_form_is(
    simplified: str, traditional: str, needs_fresh_data: bool
) -> None:
    assert demands_external_evidence(simplified) is needs_fresh_data
    assert demands_external_evidence(traditional) is needs_fresh_data
