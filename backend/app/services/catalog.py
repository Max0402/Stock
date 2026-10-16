"""
大型藍籌股清單（推薦區用）+ 常見股票的中文名稱。

基本面簡介是「靜態文字」：描述公司在做什麼（不會過時）；
價格、訊號、新聞情緒則是每次 API 呼叫時「動態」計算。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    symbol: str
    name: str
    sector: str
    description: str
    news_query: str  # Google News 搜尋字串（台股用中文名比代碼準；不要加 "stock" 這種泛用字，會搜到無關的報價頁）
    # 相關性關鍵字：新聞標題至少要出現其中一個，才算「跟這檔股票有關」
    # （英文以完整單字比對，不分大小寫；中文直接比對字串）
    keywords: tuple[str, ...] = ()


BLUE_CHIPS: list[CatalogEntry] = [
    # ── 美股 ───────────────────────────────────────────
    CatalogEntry("NVDA", "NVIDIA 輝達", "半導體 / AI",
                 "全球 GPU 與 AI 加速器龍頭，資料中心業務是主要成長引擎，CUDA 生態系形成高轉換成本護城河。",
                 "NVIDIA OR NVDA", ("nvidia", "nvda", "輝達")),
    CatalogEntry("TSLA", "Tesla 特斯拉", "電動車 / 能源",
                 "電動車領導品牌，另有儲能與自駕軟體業務；股價波動大，市場高度關注交車量與毛利率。",
                 "Tesla OR TSLA", ("tesla", "tsla", "特斯拉")),
    CatalogEntry("AAPL", "Apple 蘋果", "消費電子",
                 "iPhone、Mac 與穿戴裝置為核心，App Store、iCloud 等服務營收提供穩定且高毛利的現金流。",
                 "Apple OR AAPL", ("apple", "aapl", "蘋果")),
    CatalogEntry("MSFT", "Microsoft 微軟", "軟體 / 雲端",
                 "Azure 雲端、Office 365 與企業軟體龍頭，積極將生成式 AI（Copilot）整合進全產品線。",
                 "Microsoft OR MSFT", ("microsoft", "msft", "微軟")),
    CatalogEntry("GOOGL", "Alphabet (Google)", "網路 / 廣告",
                 "搜尋廣告與 YouTube 為主要營收，Google Cloud 與自研 AI 晶片（TPU）是長期成長動能。",
                 "Alphabet OR Google OR GOOGL", ("alphabet", "google", "googl", "goog")),
    CatalogEntry("AMZN", "Amazon 亞馬遜", "電商 / 雲端",
                 "全球電商龍頭，AWS 是全球最大公有雲之一，貢獻公司大部分營業利益。",
                 "Amazon OR AMZN", ("amazon", "amzn", "aws", "亞馬遜")),
    # ── 台股 ───────────────────────────────────────────
    CatalogEntry("2330.TW", "台積電", "半導體 / 晶圓代工",
                 "全球最大專業晶圓代工廠，先進製程與先進封裝（CoWoS）市占領先，是台股權值最大的公司。",
                 "台積電 OR 2330", ("台積電", "台積", "2330", "tsmc")),
    CatalogEntry("2454.TW", "聯發科", "半導體 / IC 設計",
                 "全球主要手機 SoC 供應商之一，產品涵蓋 Wi-Fi、電視晶片，並跨足車用與 AI ASIC。",
                 "聯發科 OR 2454", ("聯發科", "2454", "mediatek")),
    CatalogEntry("2317.TW", "鴻海", "電子代工 / AI 伺服器",
                 "全球最大電子代工服務（EMS）廠，近年 AI 伺服器出貨快速成長，並布局電動車平台。",
                 "鴻海 OR 2317", ("鴻海", "2317", "foxconn", "富士康")),
    CatalogEntry("2308.TW", "台達電", "電源管理 / 散熱",
                 "電源供應器與散熱解決方案大廠，受惠資料中心、電動車與綠能的長期需求。",
                 "台達電 OR 2308", ("台達電", "台達", "2308")),
    CatalogEntry("2382.TW", "廣達", "電腦代工 / AI 伺服器",
                 "全球主要筆電代工廠，雲端與 AI 伺服器業務比重持續提高。",
                 "廣達 OR 2382", ("廣達", "2382", "quanta")),
    CatalogEntry("2881.TW", "富邦金", "金融控股",
                 "台灣大型金控，旗下有富邦人壽、台北富邦銀行等，獲利與利率環境及股市表現連動。",
                 "富邦金 OR 2881", ("富邦金", "富邦", "2881", "fubon")),
]

CATALOG: dict[str, CatalogEntry] = {c.symbol: c for c in BLUE_CHIPS}
