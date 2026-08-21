#!/usr/bin/env python3
"""
data.json 生成スクリプト

index.html と同じディレクトリに data.json を出力する。
取得先は Yahoo Finance の chart エンドポイント（APIキー不要）。

    pip install requests
    python fetch_prices.py

シンボルは「論理キー: 候補の並び」で持ち、先頭から順に試して最初に
取れたものを採用する。表記が不確かな指数（TOPIX、東証REIT等）は
最後に ETF を置いてあるので、指数が取れなくても水準は追える。
採用した実シンボルは data.json の resolved に記録し、画面の個別欄に表示する。

注意:
- 当該エンドポイントは非公式であり、仕様変更・利用条件のリスクがある。
  対外配信や社内正式利用に載せるならデータベンダー契約に切り替えること。
"""

import json
import sys
import time
from collections import OrderedDict
from datetime import datetime, timezone, timedelta

import requests

JST = timezone(timedelta(hours=9))

# 論理キー: 候補シンボル（先頭優先）
INSTRUMENTS = OrderedDict([
    # 日本
    ("^N225",     ["^N225"]),
    ("^TPX",      ["TOPIX.T", "^TPX", "998405.T", "1306.T"]),   # 最後は ETF で代用
    ("^NKVI",     ["^NKVI.OS", "^NKVF.OS"]),                    # 日経平均VI
    ("^TREIT",    ["^TREIT", "TREIT.T"]),                       # 東証REIT指数（ETF代用はしない）
    ("NIY=F",     ["NIY=F"]),
    ("NKD=F",     ["NKD=F"]),
    # 米国
    ("^DJI",      ["^DJI"]),
    ("^IXIC",     ["^IXIC"]),
    ("^GSPC",     ["^GSPC"]),
    ("^RUT",      ["^RUT"]),
    ("^SOX",      ["^SOX"]),
    ("^VIX",      ["^VIX"]),
    ("^TNX",      ["^TNX"]),
    # 先物
    ("YM=F",      ["YM=F"]),
    ("ES=F",      ["ES=F"]),
    ("NQ=F",      ["NQ=F"]),
    ("RTY=F",     ["RTY=F"]),
    ("VX=F",      ["VX=F", "^VIX"]),
    ("ZN=F",      ["ZN=F"]),
    ("DX=F",      ["DX=F", "DX-Y.NYB"]),
    # 欧州・アジア
    ("^FTSE",     ["^FTSE"]),
    ("^GDAXI",    ["^GDAXI"]),
    ("^FCHI",     ["^FCHI"]),
    ("^STOXX50E", ["^STOXX50E"]),
    ("^HSI",      ["^HSI"]),
    ("000001.SS", ["000001.SS"]),
    ("^KS11",     ["^KS11"]),
    ("^TWII",     ["^TWII"]),
    ("^NSEI",     ["^NSEI"]),
    ("^AXJO",     ["^AXJO"]),
    # 為替・商品
    ("JPY=X",     ["JPY=X"]),
    ("EURJPY=X",  ["EURJPY=X"]),
    ("EURUSD=X",  ["EURUSD=X"]),
    ("GBPJPY=X",  ["GBPJPY=X"]),
    ("AUDJPY=X",  ["AUDJPY=X"]),
    ("GC=F",      ["GC=F"]),
    ("SI=F",      ["SI=F"]),
    ("CL=F",      ["CL=F"]),
    ("BTC-JPY",   ["BTC-JPY"]),
])

ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
PARAMS = {"range": "1d", "interval": "5m", "includePrePost": "true"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sekai-board/1.0)"}
MAX_POINTS = 160


def thin(seq, n=MAX_POINTS):
    """点数が多すぎる場合に等間隔で間引く。"""
    if len(seq) <= n:
        return seq
    step = len(seq) / n
    return [seq[int(i * step)] for i in range(n)]


def fetch_one(symbol, session):
    r = session.get(ENDPOINT.format(symbol), params=PARAMS,
                    headers=HEADERS, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    meta = res["meta"]
    closes = res["indicators"]["quote"][0].get("close") or []
    series = [c for c in closes if c is not None]
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError("現在値なし")

    return {
        "price": price,
        "prev": meta.get("chartPreviousClose") or meta.get("previousClose"),
        "high": meta.get("regularMarketDayHigh") or (max(series) if series else None),
        "low": meta.get("regularMarketDayLow") or (min(series) if series else None),
        "open": series[0] if series else None,
        "volume": meta.get("regularMarketVolume"),
        "series": [round(v, 6) for v in thin(series)],
        "time": datetime.fromtimestamp(
            meta.get("regularMarketTime") or time.time(), JST).isoformat(),
    }


def main(out_path="data.json"):
    session = requests.Session()
    quotes, resolved, failed = {}, {}, []

    for key, candidates in INSTRUMENTS.items():
        errors = []
        for sym in candidates:
            try:
                quotes[key] = fetch_one(sym, session)
                resolved[key] = sym
                break
            except Exception as e:
                errors.append(f"{sym}({e})")
            finally:
                time.sleep(0.3)          # レート制限への配慮
        else:
            failed.append(f"{key}: " + " / ".join(errors))
            print(f"[warn] {key} 取得失敗: {errors}", file=sys.stderr)

    payload = {
        "asOf": datetime.now(JST).isoformat(),
        "source": "Yahoo Finance (非公式エンドポイント)",
        "resolved": resolved,
        "failed": failed,
        "quotes": quotes,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(quotes)}/{len(INSTRUMENTS)} 銘柄を {out_path} に書き出した")
    for k, v in resolved.items():
        if v != k:
            print(f"  代替採用 {k} -> {v}")
    if failed:
        print("取得失敗: " + "; ".join(failed))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data.json")
