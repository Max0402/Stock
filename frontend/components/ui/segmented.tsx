"use client";

// 分段切換按鈕（類似 shadcn 的 Tabs / ToggleGroup），用在「日K / 週K」「美股 / 台股」。

import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
  ariaLabel,
}: {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("inline-flex rounded-lg bg-muted p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-colors",
            value === o.value ? "bg-card text-foreground shadow" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
