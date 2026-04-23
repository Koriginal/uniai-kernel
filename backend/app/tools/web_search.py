import asyncio
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, quote_plus, unquote, urlencode, urlparse, urlunparse

import httpx

from app.core.config import settings
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


# 进程内轻量缓存：减少热点问题重复联网开销
_SEARCH_CACHE: Dict[str, Tuple[float, str]] = {}


class WebSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="web_search",
            label="互联网搜索",
            description=(
                "用于检索最新事实、价格、新闻、公告、政策等实时信息。"
                "返回结构化证据（标题、摘要、来源、链接、引用编号），可直接被智能体用于回答。"
            ),
            category="knowledge",
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要搜索的关键词或问题。"},
                "top_k": {
                    "type": "integer",
                    "description": "最终返回条数，默认 5，范围 1-10。",
                    "minimum": 1,
                    "maximum": 10,
                },
                "recency_days": {
                    "type": "integer",
                    "description": "可选，优先近期结果（仅部分搜索后端生效）。",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, **kwargs) -> str:
        q = (query or "").strip()
        if not q:
            return "搜索失败：query 不能为空。"

        top_k = self._clamp_int(kwargs.get("top_k", 5), 1, 10, 5)
        recency_days_raw = kwargs.get("recency_days")
        recency_days = self._clamp_int(recency_days_raw, 1, 30, None) if recency_days_raw is not None else None
        provider = (settings.WEB_SEARCH_PROVIDER or "auto").lower()
        timeout = float(settings.WEB_SEARCH_TIMEOUT_SECONDS or 15.0)
        max_candidates = max(3, int(settings.WEB_SEARCH_MAX_CANDIDATES or 12))
        max_page_fetch = max(0, int(settings.WEB_SEARCH_MAX_PAGE_FETCH or 6))
        page_char_limit = max(500, int(settings.WEB_SEARCH_PAGE_CHAR_LIMIT or 3000))
        cache_ttl = max(0, int(settings.WEB_SEARCH_CACHE_TTL_SECONDS or 300))
        blocked_domains = {
            d.strip().lower()
            for d in (settings.WEB_SEARCH_BLOCKED_DOMAINS or "").split(",")
            if d.strip()
        }
        cache_key = f"{provider}|{q}|{top_k}|{recency_days}|{max_candidates}|{max_page_fetch}"

        cached = self._cache_get(cache_key, cache_ttl)
        if cached:
            logger.info(f"[WebSearchTool] cache hit query={q!r}")
            return cached

        logger.info(
            f"[WebSearchTool] query={q!r}, top_k={top_k}, provider={provider}, "
            f"recency_days={recency_days}, max_candidates={max_candidates}, max_page_fetch={max_page_fetch}"
        )

        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "UniAI-Kernel/1.0"}) as client:
                candidates, used_backends = await self._recall_candidates(
                    client=client,
                    query=q,
                    provider=provider,
                    recency_days=recency_days,
                    max_candidates=max_candidates,
                    blocked_domains=blocked_domains,
                )

                if not candidates:
                    result = self._no_result_fallback(q)
                    self._cache_set(cache_key, result)
                    return result

                if settings.WEB_SEARCH_ENABLE_PAGE_FETCH and max_page_fetch > 0:
                    await self._enrich_with_page_content(
                        client=client,
                        docs=candidates[:max_page_fetch],
                        char_limit=page_char_limit,
                    )

                ranked = self._rank_documents(query=q, docs=candidates)
                selected = ranked[:top_k]
                output = self._format_output(query=q, docs=selected, backends=used_backends)
                self._cache_set(cache_key, output)
                return output
        except Exception as e:
            logger.error(f"[WebSearchTool] Error: {e}")
            return f"联网搜索功能异常：{e}"

    async def _recall_candidates(
        self,
        client: httpx.AsyncClient,
        query: str,
        provider: str,
        recency_days: Optional[int],
        max_candidates: int,
        blocked_domains: set[str],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        docs: List[Dict[str, Any]] = []
        used_backends: List[str] = []

        async def try_backend(name: str, coro):
            try:
                items = await coro
                if items:
                    used_backends.append(name)
                    docs.extend(items)
            except Exception as e:
                logger.warning(f"[WebSearchTool] backend {name} failed: {e}")

        if provider == "auto":
            if settings.TAVILY_API_KEY:
                await try_backend("tavily", self._search_tavily(client, query, max_candidates, recency_days))
            if settings.SERPER_API_KEY:
                await try_backend("serper", self._search_serper(client, query, max_candidates))
            # auto 模式始终补充一个开放后端，增强覆盖
            await try_backend("duckduckgo", self._search_duckduckgo_html(client, query, max_candidates))
        elif provider == "tavily":
            await try_backend("tavily", self._search_tavily(client, query, max_candidates, recency_days))
        elif provider == "serper":
            await try_backend("serper", self._search_serper(client, query, max_candidates))
        else:
            await try_backend("duckduckgo", self._search_duckduckgo_html(client, query, max_candidates))

        dedup = self._dedup_documents(docs, blocked_domains)
        return dedup[:max_candidates], used_backends

    async def _search_tavily(
        self, client: httpx.AsyncClient, query: str, limit: int, recency_days: Optional[int]
    ) -> List[Dict[str, Any]]:
        if not settings.TAVILY_API_KEY:
            return []
        payload: Dict[str, Any] = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "max_results": limit,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }
        if recency_days:
            payload["days"] = recency_days

        resp = await client.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        data = resp.json() or {}
        out: List[Dict[str, Any]] = []
        for item in data.get("results", []) or []:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            out.append(
                {
                    "title": item.get("title") or "",
                    "snippet": item.get("content") or "",
                    "url": url,
                    "source": self._extract_domain(url) or "tavily",
                    "backend": "tavily",
                }
            )
        return out

    async def _search_serper(self, client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
        if not settings.SERPER_API_KEY:
            return []
        headers = {"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"}
        payload = {"q": query, "num": limit}
        resp = await client.post("https://google.serper.dev/search", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json() or {}
        out: List[Dict[str, Any]] = []
        for item in data.get("organic", []) or []:
            url = (item.get("link") or "").strip()
            if not url:
                continue
            out.append(
                {
                    "title": item.get("title") or "",
                    "snippet": item.get("snippet") or "",
                    "url": url,
                    "source": self._extract_domain(url) or "serper",
                    "backend": "serper",
                }
            )
        return out

    async def _search_duckduckgo_html(self, client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        body = resp.text or ""

        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
            re.S,
        )
        out: List[Dict[str, Any]] = []
        for match in pattern.finditer(body):
            href = html.unescape(match.group("href") or "").strip()
            real_url = self._unwrap_ddg_redirect(href) or href
            if not real_url.startswith("http"):
                continue
            title = self._strip_html(match.group("title") or "")
            snippet = self._strip_html(match.group("snippet") or "")
            out.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": real_url,
                    "source": self._extract_domain(real_url) or "duckduckgo",
                    "backend": "duckduckgo",
                }
            )
            if len(out) >= limit:
                break
        return out

    async def _enrich_with_page_content(
        self, client: httpx.AsyncClient, docs: List[Dict[str, Any]], char_limit: int
    ) -> None:
        sem = asyncio.Semaphore(4)

        async def fetch_one(doc: Dict[str, Any]):
            async with sem:
                url = doc.get("url", "")
                if not url:
                    return
                try:
                    resp = await client.get(url, follow_redirects=True)
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "text/html" not in ctype and "text/plain" not in ctype:
                        return
                    text = self._extract_main_text(resp.text or "")
                    if not text:
                        return
                    doc["content"] = text[:char_limit]
                    # 内容丰富后可补摘要
                    if not doc.get("snippet"):
                        doc["snippet"] = text[:220]
                except Exception as e:
                    logger.debug(f"[WebSearchTool] content fetch failed url={url}: {e}")

        await asyncio.gather(*(fetch_one(d) for d in docs))

    def _rank_documents(self, query: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tokens = self._tokenize(query)
        year_now = time.gmtime().tm_year

        def score(doc: Dict[str, Any]) -> float:
            title = (doc.get("title") or "").lower()
            snippet = (doc.get("snippet") or "").lower()
            content = (doc.get("content") or "").lower()
            source = (doc.get("source") or "").lower()
            text = " ".join([title, snippet, content])

            overlap = sum(1 for t in tokens if t and t in text)
            title_overlap = sum(1 for t in tokens if t and t in title)
            snippet_overlap = sum(1 for t in tokens if t and t in snippet)
            content_bonus = min(len(content) / 1000.0, 2.0)

            authority_bonus = 0.0
            if any(x in source for x in [".gov", ".edu", "reuters.com", "bloomberg.com", "wsj.com", "ft.com"]):
                authority_bonus += 1.0
            if any(x in source for x in ["wikipedia.org", "investing.com", "finance.yahoo.com"]):
                authority_bonus += 0.6

            recency_bonus = 0.0
            if str(year_now) in text:
                recency_bonus += 0.6
            if str(year_now - 1) in text:
                recency_bonus += 0.2

            return (overlap * 1.3) + (title_overlap * 1.8) + (snippet_overlap * 1.2) + content_bonus + authority_bonus + recency_bonus

        ranked = sorted(docs, key=score, reverse=True)
        for idx, doc in enumerate(ranked, start=1):
            doc["rank"] = idx
        return ranked

    def _format_output(self, query: str, docs: List[Dict[str, Any]], backends: List[str]) -> str:
        backend_str = ",".join(backends) if backends else "unknown"
        lines = [f"【联网检索证据 | query={query} | backends={backend_str}】"]
        lines.append("请优先基于以下证据回答，并在结论中标注引用编号。")
        for i, doc in enumerate(docs, start=1):
            title = self._clean(doc.get("title") or "Untitled")
            snippet = self._clean(doc.get("snippet") or "") or "(无摘要)"
            if len(snippet) > 280:
                snippet = snippet[:280] + "..."
            url = doc.get("url") or ""
            source = self._clean(doc.get("source") or "unknown")
            lines.append(f"[{i}] {title}\n摘要: {snippet}\n来源: {source}\n链接: {url}")
        return "\n".join(lines)

    def _dedup_documents(self, docs: List[Dict[str, Any]], blocked_domains: set[str]) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for doc in docs:
            raw_url = (doc.get("url") or "").strip()
            if not raw_url:
                continue
            url = self._normalize_url(raw_url)
            domain = self._extract_domain(url)
            if domain in blocked_domains:
                continue
            key = (url, self._clean(doc.get("title") or ""))
            if key in seen:
                continue
            seen.add(key)
            doc["url"] = url
            doc["source"] = doc.get("source") or domain
            out.append(doc)
        return out

    def _normalize_url(self, url: str) -> str:
        try:
            parsed = urlparse(url.strip())
            if parsed.scheme not in {"http", "https"}:
                return url
            cleaned_query = [
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=False)
                if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
            ]
            normalized = parsed._replace(query=urlencode(cleaned_query), fragment="")
            return urlunparse(normalized)
        except Exception:
            return url

    def _extract_main_text(self, raw_html: str) -> str:
        # 简单正文抽取：去脚本样式、去标签、压缩空白
        content = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw_html or "")
        content = re.sub(r"(?is)<style.*?>.*?</style>", " ", content)
        content = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", content)
        content = re.sub(r"(?is)<svg.*?>.*?</svg>", " ", content)
        content = re.sub(r"(?is)<[^>]+>", " ", content)
        content = html.unescape(content)
        content = re.sub(r"\s+", " ", content).strip()
        return content

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        lowered = (text or "").lower()
        en_tokens = re.findall(r"[a-z0-9]{2,}", lowered)
        zh_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
        tokens = en_tokens + zh_chunks
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _unwrap_ddg_redirect(url: str) -> str:
        m = re.search(r"[?&]uddg=([^&]+)", url)
        if not m:
            return url
        try:
            return unquote(m.group(1))
        except Exception:
            return url

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            return (urlparse(url).netloc or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _strip_html(raw: str) -> str:
        text = re.sub(r"<[^>]+>", "", raw or "")
        return html.unescape(text).replace("\n", " ").strip()

    @staticmethod
    def _clean(raw: str) -> str:
        return html.unescape((raw or "").replace("\n", " ").strip())

    @staticmethod
    def _clamp_int(raw: Any, min_v: int, max_v: int, default: Optional[int]) -> Optional[int]:
        try:
            val = int(raw)
        except Exception:
            return default
        return max(min_v, min(max_v, val))

    @staticmethod
    def _no_result_fallback(query: str) -> str:
        encoded_q = quote_plus(query)
        return (
            "【联网检索证据】\n"
            "未检索到可解析结果。\n"
            f"可手动核查：\n[1] https://duckduckgo.com/?q={encoded_q}\n[2] https://www.google.com/search?q={encoded_q}"
        )

    @staticmethod
    def _cache_get(key: str, ttl_seconds: int) -> Optional[str]:
        if ttl_seconds <= 0:
            return None
        hit = _SEARCH_CACHE.get(key)
        if not hit:
            return None
        ts, value = hit
        if (time.time() - ts) > ttl_seconds:
            _SEARCH_CACHE.pop(key, None)
            return None
        return value

    @staticmethod
    def _cache_set(key: str, value: str) -> None:
        _SEARCH_CACHE[key] = (time.time(), value)
