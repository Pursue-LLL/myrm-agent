# Web Scraping 技能实战避坑与经验库 (Experience Library)

> 本文档遵循 Myrm 技能包内嵌经验库自闭环机制 (Read-First, Write-Back Loop)。
> Agent 在执行抓取任务前【必须先读】本文档，在遭遇新环境/新陷阱并解决后【必须回写】沉淀。

---

## 核心避坑条目

### 1. 【动态渲染与反爬拦截】SPA 单页应用与 Cloudflare 质检页面
- **常见踩坑/错误现象**：使用 `web_fetch_tool` 或普通 `curl` 请求返回 403 Forbidden，或仅得到空的 `<div id="app"></div>` 骨架屏，未获取有效内容。
- **根本原因 (Root Cause)**：目标站点依赖前端 JavaScript 异步水合，或部署了 Cloudflare Turnstile / 5s 盾，纯 HTTP 请求无法执行 JS 和完成质检。
- **防范铁律 / 经检验的最优解**：
  - 先尝试 `web_fetch_tool`；若响应状态码非 200 或正文缺乏关键 DOM，立刻切轨至 `browser_navigate_tool`；
  - 启动真实浏览器会话，等待网络空闲（`networkidle`）或目标核心选择器显式出现后再提取 `document.body.innerText` 或 outerHTML。

---

### 2. 【编码陷阱】部分老旧中文站点 GBK / GB2312 乱码
- **常见踩坑/错误现象**：抓取政府、传统企业或高校网站时，控制台输出大量的 `` 乱码字符。
- **根本原因 (Root Cause)**：HTTP 响应头未声明 `charset=utf-8`，或响应正文 `<meta charset="gb2312">` 未被 Python requests 自动正确识别（requests 默认 fallback 到 ISO-8859-1）。
- **防范铁律 / 经检验的最优解**：
  - 必须显式检测编码：`response.encoding = response.apparent_encoding`；
  - 或者在解析 HTML 时使用 `BeautifulSoup(content, 'html.parser', from_encoding='gb18030')`，包容 GBK/GB2312/GB18030 字符集。

---

### 3. 【频控与封锁】连续请求导致 IP 被限流 (429 Too Many Requests)
- **常见踩坑/错误现象**：短时间内批量抓取分页时，第 3~5 页起全部报错 429 或被要求输入图形验证码。
- **根本原因 (Root Cause)**：没有添加适当的请求间隔抖动，高并发请求触发了目标服务的 WAF 频控阈值。
- **防范铁律 / 经检验的最优解**：
  - 严格限制并发度（推荐串行或并发不超过 2）；
  - 在请求间注入随机抖动延时：`time.sleep(random.uniform(1.2, 3.5))`；
  - 始终携带合理的 `User-Agent` 与 `Referer` 标头，模拟真实浏览器访问。
