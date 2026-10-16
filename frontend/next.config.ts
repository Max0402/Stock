import type { NextConfig } from "next";

// 兩種模式：
//
// 1. 本機開發（npm run dev）：
//    前端呼叫 /api/* 時，由 Next.js 轉發到 FastAPI（預設 http://localhost:8000）。
//    瀏覽器只跟同一個網域溝通 → 不用處理 CORS。
//
// 2. 部署（NEXT_OUTPUT=export npm run build）：
//    把整個前端輸出成純靜態檔（out/ 資料夾），交給 FastAPI 一起提供。
//    網頁和 API 在同一個網址底下，所以 /api/* 直接就是後端，不需要轉發。
//    （這個儀表板所有資料都是在瀏覽器端用 SWR 抓的，所以可以完全靜態化。）
const isExport = process.env.NEXT_OUTPUT === "export";
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = isExport
  ? { output: "export" }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
      },
    };

export default nextConfig;
