import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui 的標準工具函式：合併 className，並解決 Tailwind class 衝突。
 * 例：cn("px-2", isBig && "px-4") → "px-4"（後面的覆蓋前面的）
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
