import { Dashboard } from "@/components/dashboard/Dashboard";

// 首頁就是儀表板。Dashboard 是 Client Component（需要互動、輪詢更新）。
export default function Home() {
  return <Dashboard />;
}
