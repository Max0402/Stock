import type { NextConfig } from "next";

// 前端呼叫 /api/* 時，由 Next.js 伺服器轉發到 FastAPI 後端。
// 好處：瀏覽器只跟同一個網域溝通 → 不用處理 CORS，也不會把後端網址暴露在前端程式碼裡。
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
