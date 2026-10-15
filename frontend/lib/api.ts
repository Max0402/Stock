// 所有跟後端溝通的程式都集中在這裡。
// 路徑都是相對的 /api/...，由 next.config.ts 的 rewrites 轉發到 FastAPI。

import { mutate } from "swr";

import type { HoldingInput } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** 把 FastAPI 的錯誤格式轉成一句人看得懂的訊息。 */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    // HTTPException → {"detail": "文字"}；欄位驗證失敗 → {"detail": [{"msg": "..."}]}
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join("；");
  } catch {
    /* 回應不是 JSON，用下面的預設訊息 */
  }
  return `請求失敗（HTTP ${res.status}）`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** SWR 用的 fetcher：useSWR("/api/portfolio", fetcher) */
export const fetcher = <T>(path: string) => request<T>(path);

/** 資料變動後，讓所有相關畫面重新抓資料（SWR 的 key 就是 API 路徑）。 */
function refreshAll() {
  return mutate(
    (key) =>
      typeof key === "string" &&
      (key.startsWith("/api/portfolio") || key.startsWith("/api/watchlist") || key.startsWith("/api/recommendations")),
  );
}

export const api = {
  async createHolding(input: HoldingInput) {
    await request("/api/holdings", { method: "POST", body: JSON.stringify(input) });
    await refreshAll();
  },
  async updateHolding(id: number, input: Partial<HoldingInput>) {
    await request(`/api/holdings/${id}`, { method: "PATCH", body: JSON.stringify(input) });
    await refreshAll();
  },
  async deleteHolding(id: number) {
    await request(`/api/holdings/${id}`, { method: "DELETE" });
    await refreshAll();
  },
  async setStarred(symbol: string, starred: boolean) {
    if (starred) {
      await request("/api/watchlist", { method: "POST", body: JSON.stringify({ symbol }) });
    } else {
      await request(`/api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" });
    }
    await refreshAll();
  },
};
