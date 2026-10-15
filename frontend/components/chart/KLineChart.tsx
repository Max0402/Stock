"use client";

// K 線圖（TradingView Lightweight Charts v5）
// ───────────────────────────────────────────
// 主圖：K 棒 + 成交量 + MA5/20/60 + 布林通道 + ▲▼ 買賣訊號標記
//       + 價位線：買進區上下緣、停利（TP）、停損（SL）
// 副圖：RSI(14) 與 70 / 30 超買超賣線
//
// React + Canvas 圖表的關鍵觀念：
//   圖表不是 React 元件，而是「命令式 API」畫在 <div> 裡。
//   → 用 useRef 拿到 DOM，在 useEffect 裡建立圖表，元件卸載時 chart.remove() 釋放記憶體。

import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  LineSeries,
  LineStyle,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { SignalBadge } from "@/components/dashboard/SignalBadge";
import { Card } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { formatPct, formatPrice } from "@/lib/format";
import { useMarketColors } from "@/lib/market-colors";
import type { ChartData, Interval, LinePoint } from "@/lib/types";
import { cn } from "@/lib/utils";

// 與 globals.css 的 --color-zone / target / stop 相同（canvas 無法直接讀 Tailwind class）
const COLORS = {
  zone: "#38bdf8",
  target: "#fbbf24",
  stop: "#e879f9",
  ma5: "#f472b6",
  ma20: "#facc15",
  ma60: "#a78bfa",
  bb: "#64748b",
  rsi: "#38bdf8",
  text: "#8b95a7",
  grid: "rgba(139,149,167,0.08)",
};

const VISIBLE_BARS: Record<Interval, number> = { "1d": 120, "1wk": 104 };

type Toggle = "ma" | "bb" | "rsi" | "markers" | "levels";
const TOGGLES: { key: Toggle; label: string }[] = [
  { key: "ma", label: "MA" },
  { key: "bb", label: "布林" },
  { key: "rsi", label: "RSI" },
  { key: "markers", label: "訊號" },
  { key: "levels", label: "價位線" },
];

interface SeriesRefs {
  candle: ISeriesApi<"Candlestick">;
  ma: ISeriesApi<"Line">[];
  bb: ISeriesApi<"Line">[];
  rsi?: ISeriesApi<"Line">;
  markers: ISeriesMarkersPluginApi<Time>;
  priceLines: IPriceLine[];
}

const toLine = (pts: LinePoint[]) => pts.map((p) => ({ time: p.time as Time, value: p.value }));

export function KLineChart({ symbol }: { symbol: string }) {
  const [interval, setChartInterval] = useState<Interval>("1d");
  const [show, setShow] = useState<Record<Toggle, boolean>>({
    ma: true,
    bb: false,
    rsi: true,
    markers: true,
    levels: true,
  });
  const { upHex, downHex } = useMarketColors();

  const { data, error, isLoading } = useSWR<ChartData>(
    `/api/stocks/${encodeURIComponent(symbol)}/chart?interval=${interval}`,
    { refreshInterval: 15 * 60_000, keepPreviousData: true },
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesRefs | null>(null);
  const [legend, setLegend] = useState<{ o: number; h: number; l: number; c: number; chg: number } | null>(null);

  const currency = symbol.endsWith(".TW") || symbol.endsWith(".TWO") ? "TWD" : "USD";

  // ① 資料或顏色改變 → 重建整張圖
  useEffect(() => {
    const el = containerRef.current;
    if (!el || !data || data.candles.length === 0) return;

    const chart = createChart(el, {
      autoSize: true, // 跟著容器大小自動縮放（RWD）
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: COLORS.text,
        fontSize: 11,
        panes: { separatorColor: "#1f2a3d" },
      },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1f2a3d" },
      timeScale: { borderColor: "#1f2a3d", rightOffset: 4 },
    });
    chartRef.current = chart;

    // K 棒（顏色依漲跌慣例）
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: upHex,
      downColor: downHex,
      wickUpColor: upHex,
      wickDownColor: downHex,
      borderVisible: false,
    });
    candle.setData(data.candles.map((c) => ({ ...c, time: c.time as Time })));

    // 成交量：疊在主圖底部 20% 的獨立價格軸
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" } });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      data.candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: (c.close >= c.open ? upHex : downHex) + "55", // 加上透明度
      })),
    );

    const line = (color: string, width: 1 | 2 = 1, style = LineStyle.Solid) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });

    const ma = [
      [line(COLORS.ma5), data.indicators.ma5],
      [line(COLORS.ma20, 2), data.indicators.ma20],
      [line(COLORS.ma60, 2), data.indicators.ma60],
    ] as const;
    ma.forEach(([s, pts]) => s.setData(toLine(pts)));

    const bb = [
      [line(COLORS.bb, 1, LineStyle.Dashed), data.indicators.bb_upper],
      [line(COLORS.bb, 1, LineStyle.Dotted), data.indicators.bb_mid],
      [line(COLORS.bb, 1, LineStyle.Dashed), data.indicators.bb_lower],
    ] as const;
    bb.forEach(([s, pts]) => s.setData(toLine(pts)));

    seriesRef.current = {
      candle,
      ma: ma.map(([s]) => s),
      bb: bb.map(([s]) => s),
      markers: createSeriesMarkers(candle, []),
      priceLines: [],
    };

    // 預設只顯示最近 N 根（日 K 約半年、週 K 約兩年），可以用滑鼠拖曳 / 滾輪看更早
    const n = data.candles.length;
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - VISIBLE_BARS[data.interval]), to: n + 3 });

    // 十字線移動 → 更新左上角 OHLC 圖例
    const last = data.candles[n - 1];
    const prev = data.candles[n - 2] ?? last;
    const fallback = { o: last.open, h: last.high, l: last.low, c: last.close, chg: (last.close / prev.close - 1) * 100 };
    setLegend(fallback);
    chart.subscribeCrosshairMove((param) => {
      const bar = param.seriesData.get(candle) as { open: number; high: number; low: number; close: number } | undefined;
      if (!bar) return setLegend(fallback);
      setLegend({ o: bar.open, h: bar.high, l: bar.low, c: bar.close, chg: (bar.close / bar.open - 1) * 100 });
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [data, upHex, downHex]);

  // ② 切換顯示項目 → 只改可見度，不重建圖表（保留使用者縮放的位置）
  useEffect(() => {
    const chart = chartRef.current;
    const s = seriesRef.current;
    if (!chart || !s || !data) return;

    s.ma.forEach((x) => x.applyOptions({ visible: show.ma }));
    s.bb.forEach((x) => x.applyOptions({ visible: show.bb }));

    // ▲ 買進 / ▼ 賣出 標記（演算法在歷史上「分數穿越門檻」的位置）
    const markers: SeriesMarker<Time>[] = show.markers
      ? data.markers.map((m) =>
          m.type === "BUY"
            ? { time: m.time as Time, position: "belowBar", shape: "arrowUp", color: COLORS.zone, text: "B" }
            : { time: m.time as Time, position: "aboveBar", shape: "arrowDown", color: COLORS.target, text: "S" },
        )
      : [];
    s.markers.setMarkers(markers);

    // 價位線：買進區上下緣、停利、停損
    s.priceLines.forEach((pl) => s.candle.removePriceLine(pl));
    s.priceLines = [];
    const sig = data.signal;
    if (show.levels && sig) {
      const add = (price: number, color: string, title: string, style = LineStyle.Dashed) =>
        s.priceLines.push(
          s.candle.createPriceLine({ price, color, title, lineWidth: 1, lineStyle: style, axisLabelVisible: true }),
        );
      add(sig.buy_zone_high, COLORS.zone, "買進區↑", LineStyle.Dotted);
      add(sig.buy_zone_low, COLORS.zone, "買進區↓", LineStyle.Dotted);
      add(sig.take_profit, COLORS.target, "停利 TP");
      add(sig.stop_loss, COLORS.stop, "停損 SL");
    }

    // RSI 副圖（pane 1）：開啟時新增、關閉時移除（pane 沒有 series 會自動消失）
    if (show.rsi && !s.rsi) {
      const rsi = chart.addSeries(
        LineSeries,
        { color: COLORS.rsi, lineWidth: 1, priceLineVisible: false, lastValueVisible: true },
        1,
      );
      rsi.setData(toLine(data.indicators.rsi));
      rsi.createPriceLine({ price: 70, color: upHex, lineStyle: LineStyle.Dashed, lineWidth: 1, title: "超買 70", axisLabelVisible: false });
      rsi.createPriceLine({ price: 30, color: downHex, lineStyle: LineStyle.Dashed, lineWidth: 1, title: "超賣 30", axisLabelVisible: false });
      chart.panes()[1]?.setHeight(110);
      s.rsi = rsi;
    } else if (!show.rsi && s.rsi) {
      chart.removeSeries(s.rsi);
      s.rsi = undefined;
    }
  }, [data, show, upHex, downHex]);

  const sig = data?.signal;
  const lastRsi = useMemo(() => data?.indicators.rsi.at(-1)?.value, [data]);

  return (
    <Card id="chart" className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 pb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold">{symbol}</h2>
            {data?.symbol === symbol && <span className="truncate text-sm text-muted-foreground">{data.name}</span>}
            {sig && <SignalBadge action={sig.action} score={sig.score} />}
          </div>
          {legend && (
            <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground tabular">
              <span>開 {formatPrice(legend.o, currency)}</span>
              <span>高 {formatPrice(legend.h, currency)}</span>
              <span>低 {formatPrice(legend.l, currency)}</span>
              <span>收 {formatPrice(legend.c, currency)}</span>
              <span className={legend.chg >= 0 ? "text-up" : "text-down"}>{formatPct(legend.chg)}</span>
              {show.rsi && lastRsi != null && <span style={{ color: COLORS.rsi }}>RSI {lastRsi.toFixed(1)}</span>}
            </div>
          )}
        </div>
        <Segmented
          ariaLabel="K 線週期"
          value={interval}
          onChange={setChartInterval}
          options={[
            { value: "1d", label: "日K" },
            { value: "1wk", label: "週K" },
          ]}
        />
      </div>

      {/* 指標開關 */}
      <div className="flex flex-wrap items-center gap-1.5 px-4 pb-2">
        {TOGGLES.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-pressed={show[t.key]}
            onClick={() => setShow((s) => ({ ...s, [t.key]: !s[t.key] }))}
            className={cn(
              "cursor-pointer rounded-full border px-2.5 py-0.5 text-xs transition-colors",
              show[t.key]
                ? "border-primary/60 bg-primary/15 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
        {show.ma && (
          <span className="ml-1 flex gap-2 text-[11px] tabular">
            <span style={{ color: COLORS.ma5 }}>MA5</span>
            <span style={{ color: COLORS.ma20 }}>MA20</span>
            <span style={{ color: COLORS.ma60 }}>MA60</span>
          </span>
        )}
      </div>

      <div className="relative h-[420px] w-full sm:h-[480px]">
        <div ref={containerRef} className="absolute inset-0" />
        {(isLoading || error) && !data && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            {error ? `無法載入 K 線：${error.message}` : "載入 K 線中…"}
          </div>
        )}
      </div>

      {/* 價位圖例 */}
      {sig && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2.5 text-xs tabular">
          <span style={{ color: COLORS.zone }}>
            ▲ 買進區 {formatPrice(sig.buy_zone_low, currency)}–{formatPrice(sig.buy_zone_high, currency)}
          </span>
          <span style={{ color: COLORS.target }}>━ 停利 {formatPrice(sig.take_profit, currency)}</span>
          <span style={{ color: COLORS.stop }}>━ 停損 {formatPrice(sig.stop_loss, currency)}</span>
          <span className="text-muted-foreground">
            依{data?.interval === "1wk" ? "週" : "日"} K 計算 · B / S = 歷史技術訊號（分數穿越 ±2）
          </span>
        </div>
      )}
    </Card>
  );
}
