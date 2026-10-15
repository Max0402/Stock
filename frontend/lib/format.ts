// 數字 / 金額 / 時間的格式化工具（用瀏覽器內建的 Intl API，自動處理千分位）。

const moneyFormatters = new Map<string, Intl.NumberFormat>();

export function formatMoney(value: number | null | undefined, currency: string, compact = false): string {
  if (value == null || Number.isNaN(value)) return "—";
  const key = `${currency}-${compact}`;
  if (!moneyFormatters.has(key)) {
    moneyFormatters.set(
      key,
      new Intl.NumberFormat("zh-TW", {
        style: "currency",
        currency,
        notation: compact ? "compact" : "standard",
        // 台幣金額通常不看小數；美元看到「分」
        maximumFractionDigits: currency === "TWD" ? 0 : 2,
        minimumFractionDigits: currency === "TWD" ? 0 : 2,
      }),
    );
  }
  return moneyFormatters.get(key)!.format(value);
}

/** 股價：台股高價股不需要小數，低價股與美股保留 2 位 */
export function formatPrice(value: number | null | undefined, currency = "USD"): string {
  if (value == null || Number.isNaN(value)) return "—";
  const digits = currency === "TWD" && value >= 1000 ? 0 : 2;
  return value.toLocaleString("zh-TW", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** 帶正負號的百分比：+1.23% / −0.45% */
export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function formatSigned(value: number | null | undefined, currency: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  const body = formatMoney(Math.abs(value), currency);
  return value > 0 ? `+${body}` : value < 0 ? `−${body}` : body;
}

/** 台股顯示「張」：1 張 = 1000 股 */
export function formatShares(shares: number, market: "US" | "TW"): string {
  const s = shares.toLocaleString("zh-TW", { maximumFractionDigits: 4 });
  if (market === "TW" && shares >= 1000 && shares % 1000 === 0) return `${s} 股（${shares / 1000} 張）`;
  return `${s} 股`;
}

const rtf = new Intl.RelativeTimeFormat("zh-TW", { numeric: "auto" });

export function timeAgo(iso: string): string {
  const diffSec = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diffSec);
  if (abs < 60) return "剛剛";
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  return rtf.format(Math.round(diffSec / 86400), "day");
}

/** 現價距離某個價位幾 %（正 = 在價位上方） */
export function distancePct(price: number, level: number): number {
  return ((price - level) / level) * 100;
}

/**
 * 只允許 http / https 連結。
 * 新聞網址來自外部 RSS（不可信資料）—— 若直接放進 <a href>，
 * 惡意的 "javascript:alert(1)" 網址會變成 XSS 攻擊。
 */
export function safeExternalUrl(url: string): string | undefined {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : undefined;
  } catch {
    return undefined;
  }
}
