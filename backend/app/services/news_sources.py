"""
可信新聞來源白名單（Trusted Sources）。

為什麼需要白名單？
------------------
Yahoo Finance、Google News 都是「聚合器」：同一檔股票的新聞裡，
除了路透、Bloomberg 之外，也混了很多內容農場、付費推廣文、AI 自動產生的文章。
這些內容如果直接拿去算情緒分數，會讓買賣訊號被雜訊帶著跑。

所以我們只留下白名單裡的媒體（可用 NEWS_TRUSTED_ONLY=false 關閉），並分成三級：

    official       官方公告（證交所公開資訊觀測站）—— 最可靠的第一手資訊
    major          主流財經媒體 / 通訊社（路透、Bloomberg、中央社、經濟日報…）
    press_release  公司新聞稿通路（Business Wire 等）—— 第一手但偏宣傳

比對方式：發布者「名稱」或「網域」任一符合即可
（Yahoo / Finnhub 給的是名稱，Google News 的 <source url="..."> 給的是網域）。
想新增來源？直接在 TRUSTED_SOURCES 加一行即可。
"""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

Tier = Literal["official", "major", "press_release"]

# 計算「重要性」時依來源等級加分：官方公告最優先成為 Big News
TIER_BONUS: dict[str, float] = {"official": 0.8, "major": 0.3, "press_release": 0.2}
# 同一則新聞被多個來源報導時，保留等級最高的那一筆
TIER_RANK: dict[str, int] = {"official": 0, "major": 1, "press_release": 2, "other": 3}


@dataclass(frozen=True)
class TrustedSource:
    name: str                    # 統一後的顯示名稱
    tier: Tier
    domains: tuple[str, ...]     # 網域（含子網域都算，例：www.reuters.com → reuters.com）
    aliases: tuple[str, ...] = ()  # 其他寫法（比對時不分大小寫）
    market: Literal["US", "TW", "ALL"] = "ALL"  # Google News 搜尋時用哪個市場的 site: 清單


TRUSTED_SOURCES: list[TrustedSource] = [
    # ── 官方 ────────────────────────────────────────────────
    TrustedSource("公開資訊觀測站", "official", ("twse.com.tw",), ("mops", "twse", "臺灣證券交易所"), "TW"),
    # ── 國際通訊社 / 財經媒體 ─────────────────────────────────
    TrustedSource("Reuters", "major", ("reuters.com",), ("路透", "路透社"), "US"),
    TrustedSource("Bloomberg", "major", ("bloomberg.com",), ("彭博", "彭博社"), "US"),
    TrustedSource("CNBC", "major", ("cnbc.com",), (), "US"),
    TrustedSource("The Wall Street Journal", "major", ("wsj.com",), ("wall street journal", "wsj", "dow jones"), "US"),
    TrustedSource("MarketWatch", "major", ("marketwatch.com",), (), "US"),
    TrustedSource("Barron's", "major", ("barrons.com",), ("barrons",), "US"),
    TrustedSource("Financial Times", "major", ("ft.com",), ("ft",), "US"),
    TrustedSource("Associated Press", "major", ("apnews.com",), ("ap", "ap news"), "US"),
    TrustedSource("Yahoo Finance", "major", ("finance.yahoo.com",), (), "ALL"),
    TrustedSource("Investor's Business Daily", "major", ("investors.com",), ("ibd",), "ALL"),
    TrustedSource("Nikkei Asia", "major", ("asia.nikkei.com",), ("nikkei",), "ALL"),
    # ── 台灣財經媒體 ─────────────────────────────────────────
    TrustedSource("中央社", "major", ("cna.com.tw", "focustaiwan.tw"), ("中央通訊社", "cna", "focus taiwan"), "TW"),
    TrustedSource("經濟日報", "major", ("money.udn.com",), (), "TW"),
    TrustedSource("工商時報", "major", ("ctee.com.tw",), (), "TW"),
    TrustedSource("鉅亨網", "major", ("cnyes.com",), ("鉅亨", "anue鉅亨", "cnyes"), "TW"),
    TrustedSource("MoneyDJ 理財網", "major", ("moneydj.com",), ("moneydj", "moneydj理財網"), "TW"),
    TrustedSource("今周刊", "major", ("businesstoday.com.tw",), (), "TW"),
    TrustedSource("天下雜誌", "major", ("cw.com.tw",), (), "TW"),
    TrustedSource("DIGITIMES", "major", ("digitimes.com", "digitimes.com.tw"), (), "TW"),
    TrustedSource("自由財經", "major", ("ec.ltn.com.tw",), ("自由時報",), "TW"),
    # ── 公司新聞稿通路 ────────────────────────────────────────
    TrustedSource("Business Wire", "press_release", ("businesswire.com",), ("businesswire",)),
    TrustedSource("PR Newswire", "press_release", ("prnewswire.com",), ("prnewswire",)),
    TrustedSource("GlobeNewswire", "press_release", ("globenewswire.com",), ("globe newswire",)),
]


def _norm(name: str) -> str:
    return " ".join(name.lower().replace("’", "'").split())


_BY_NAME: dict[str, TrustedSource] = {}
for _s in TRUSTED_SOURCES:
    for _alias in (_s.name, *_s.aliases):
        _BY_NAME[_norm(_alias)] = _s


def _domain_matches(host: str, domain: str) -> bool:
    # 「結尾比對」要加點號：避免 evilreuters.com 被當成 reuters.com
    return host == domain or host.endswith("." + domain)


# 聚合平台：文章「放在」這些網站，不代表是它們「寫」的。
# 例如 finance.yahoo.com 上同時有 Yahoo 自己的報導，也有 Insider Monkey、Motley Fool 等轉載文章。
# 所以光看網址在這些網域，不能判斷發布者是否可信，必須看發布者名稱。
AGGREGATOR_DOMAINS = ("finance.yahoo.com", "news.google.com")


def classify_source(name: str | None, url: str | None = None) -> TrustedSource | None:
    """依發布者名稱或網址判斷是否為可信來源；不在白名單回傳 None。"""
    if name:
        hit = _BY_NAME.get(_norm(name))
        if hit:
            return hit
    if url:
        host = (urlparse(url).hostname or "").lower()
        if any(_domain_matches(host, d) for d in AGGREGATOR_DOMAINS):
            return None  # 只知道放在哪個平台、不知道是誰寫的 → 不能算可信
        for s in TRUSTED_SOURCES:
            if any(_domain_matches(host, d) for d in s.domains):
                return s
    return None


def tier_of(name: str | None, url: str | None = None) -> str:
    s = classify_source(name, url)
    return s.tier if s else "other"


def google_site_filter(market: str, limit: int = 8) -> str:
    """產生 Google News 搜尋用的 site: 篩選，例如 (site:reuters.com OR site:cnbc.com …)。"""
    domains = [s.domains[0] for s in TRUSTED_SOURCES if s.tier == "major" and s.market == market]
    return "(" + " OR ".join(f"site:{d}" for d in domains[:limit]) + ")"
