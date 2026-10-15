"use client";

// 新增 / 編輯持股的表單。
// 前端先做基本檢查（數字 > 0）提升體驗；真正的驗證一定要在後端再做一次（前端驗證可被繞過）。

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { Holding } from "@/lib/types";

const inputClass =
  "h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-60";

export function HoldingFormDialog({
  open,
  onClose,
  editing,
}: {
  open: boolean;
  onClose: () => void;
  editing: Holding | null; // null = 新增模式
}) {
  const [symbol, setSymbol] = useState("");
  const [shares, setShares] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [avgCost, setAvgCost] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // 每次打開時，用目前要編輯的持股填入表單（或清空）
  useEffect(() => {
    if (!open) return;
    setSymbol(editing?.symbol ?? "");
    setShares(editing ? String(editing.shares) : "");
    setBuyPrice(editing ? String(editing.buy_price) : "");
    setAvgCost(editing ? String(editing.avg_cost) : "");
    setNote(editing?.note ?? "");
    setError(null);
  }, [open, editing]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const nShares = Number(shares);
    const nBuy = Number(buyPrice);
    const nAvg = avgCost.trim() === "" ? null : Number(avgCost);
    if (!editing && !symbol.trim()) return setError("請輸入股票代碼");
    if (!(nShares > 0)) return setError("股數必須大於 0");
    if (!(nBuy > 0)) return setError("買入單價必須大於 0");
    if (nAvg !== null && !(nAvg > 0)) return setError("平均成本必須大於 0");

    setSaving(true);
    setError(null);
    try {
      const payload = { shares: nShares, buy_price: nBuy, avg_cost: nAvg ?? nBuy, note: note.trim() || null };
      if (editing) await api.updateHolding(editing.id, payload);
      else await api.createHolding({ symbol: symbol.trim(), ...payload });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={editing ? `編輯 ${editing.symbol}` : "新增持股"}>
      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block space-y-1">
          <span className="text-sm">股票代碼</span>
          <input
            className={inputClass}
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="AAPL、NVDA、2330、2454.TW"
            disabled={!!editing}
            autoFocus={!editing}
            maxLength={15}
          />
          <span className="block text-xs text-muted-foreground">台股輸入數字會自動補上 .TW；上櫃股票請輸入 .TWO</span>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block space-y-1">
            <span className="text-sm">持有股數</span>
            <input className={inputClass} inputMode="decimal" value={shares} onChange={(e) => setShares(e.target.value)} placeholder="台股 1 張 = 1000" />
          </label>
          <label className="block space-y-1">
            <span className="text-sm">買入單價</span>
            <input className={inputClass} inputMode="decimal" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} placeholder="例：185.5" />
          </label>
        </div>

        <label className="block space-y-1">
          <span className="text-sm">目前平均成本（選填）</span>
          <input className={inputClass} inputMode="decimal" value={avgCost} onChange={(e) => setAvgCost(e.target.value)} placeholder="分批買進時填寫；不填 = 買入單價" />
        </label>

        <label className="block space-y-1">
          <span className="text-sm">備註（選填）</span>
          <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="例：長期持有、存股" />
        </label>

        {error && <p className="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "儲存中…" : "儲存"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
