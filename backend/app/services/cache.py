"""
極簡的「有效期限快取」（TTL Cache）。

外部行情 API 都有流量限制，同一檔股票 1 分鐘內被查 10 次，
其實只需要真的打 1 次 API，其餘直接回傳記憶體裡的結果。
"""

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: float, max_items: int = 1024):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()  # FastAPI 同步端點會在多執行緒中執行，要加鎖

    def get_or_set(self, key: Any, factory: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > now:
                return hit[1]
        # 注意：factory（真的去打 API）放在鎖外面執行，避免一個慢請求卡住所有人
        value = factory()
        with self._lock:
            if len(self._data) >= self.max_items:
                # 超過上限就清掉過期的；還是太多就整個清空（簡單粗暴但安全）
                self._data = {k: v for k, v in self._data.items() if v[0] > now}
                if len(self._data) >= self.max_items:
                    self._data.clear()
            self._data[key] = (now + self.ttl, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
