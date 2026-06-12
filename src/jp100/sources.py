from __future__ import annotations

import json
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pandas as pd
from bs4 import BeautifulSoup

from .config import JPX_LIST_FALLBACK, JPX_LIST_PAGE, YAHOO_RANKINGS, PipelineConfig


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
QUOTE_PATTERN = re.compile(r"/quote/([0-9A-Z]+)\.T")


class DataSourceError(RuntimeError):
    """外部データ取得または解析に失敗した場合の例外。"""


def _request_bytes(url: str, timeout: int, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # ネットワーク例外は実行環境ごとに異なる
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise DataSourceError(f"データを取得できませんでした: {url} ({last_error})")


def _read_or_fetch(url: str, cache_path: Path, timeout: int) -> tuple[bytes, bool]:
    try:
        payload = _request_bytes(url, timeout)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(payload)
        return payload, False
    except DataSourceError:
        if cache_path.exists():
            return cache_path.read_bytes(), True
        raise


def _discover_jpx_excel_url(timeout: int) -> str:
    try:
        html = _request_bytes(JPX_LIST_PAGE, timeout).decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if re.search(r"\.xlsx?(?:$|\?)", href, re.IGNORECASE):
                return urljoin(JPX_LIST_PAGE, href)
    except DataSourceError:
        pass
    return JPX_LIST_FALLBACK


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str:
    normalized = {str(column).strip(): str(column) for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    raise DataSourceError(
        f"JPX銘柄一覧に必要な列がありません: {', '.join(candidates)}"
    )


def normalize_code(value: object) -> str:
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def load_jpx_list(config: PipelineConfig) -> tuple[pd.DataFrame, dict[str, object]]:
    cache_path = config.raw_dir / "jpx_list.xls"
    source_url = _discover_jpx_excel_url(config.request_timeout)
    payload, cache_used = _read_or_fetch(
        source_url, cache_path, config.request_timeout
    )
    try:
        frame = pd.read_excel(BytesIO(payload), dtype=str)
    except Exception as exc:
        raise DataSourceError(
            "JPX銘柄一覧を読み込めません。requirements.txt の xlrd を確認してください。"
        ) from exc

    columns = [str(column) for column in frame.columns]
    code_col = _pick_column(columns, ("コード",))
    name_col = _pick_column(columns, ("銘柄名", "銘柄名（日本語）"))
    market_col = _pick_column(columns, ("市場・商品区分", "市場区分"))
    industry_col = _pick_column(columns, ("33業種区分", "業種"))

    selected = frame[[code_col, name_col, market_col, industry_col]].copy()
    selected.columns = ["code", "name", "market_raw", "industry"]
    selected["code"] = selected["code"].map(normalize_code)
    selected["name"] = selected["name"].fillna("").str.strip()
    selected["industry"] = selected["industry"].fillna("未分類").str.strip()
    selected["market_raw"] = selected["market_raw"].fillna("").str.strip()
    market_pattern = "|".join(re.escape(item) for item in config.allowed_markets)
    selected = selected[
        selected["market_raw"].str.contains(market_pattern, regex=True, na=False)
        & selected["code"].str.fullmatch(r"[0-9A-Z]{4,5}", na=False)
    ].copy()
    selected["market"] = selected["market_raw"].map(_short_market_name)
    selected["ticker"] = selected["code"] + ".T"
    selected = selected.drop(columns="market_raw").drop_duplicates("code")
    selected = selected.sort_values("code").reset_index(drop=True)
    if selected.empty:
        raise DataSourceError("JPX銘柄一覧から東証普通株を抽出できませんでした。")
    return selected, {
        "source": source_url,
        "cache_used": cache_used,
        "count": int(len(selected)),
    }


def _short_market_name(value: str) -> str:
    for market in ("プライム", "スタンダード", "グロース"):
        if market in value:
            return market
    return value


def parse_yahoo_ranking(
    html: str, ranking_name: str, page: int
) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        match = QUOTE_PATTERN.search(str(link["href"]))
        if not match:
            continue
        code = normalize_code(match.group(1))
        name = link.get_text(" ", strip=True)
        if not name or code in seen:
            continue
        seen.add(code)
        rank = (page - 1) * 50 + len(rows) + 1
        rows.append(
            {
                "code": code,
                "yahoo_name": name,
                "ranking": ranking_name,
                "rank": rank,
            }
        )
        if len(rows) >= 50:
            break
    if not rows:
        raise DataSourceError(f"Yahooランキング「{ranking_name}」を解析できませんでした。")
    return pd.DataFrame(rows)


def load_yahoo_candidates(
    config: PipelineConfig,
) -> tuple[pd.DataFrame, dict[str, object]]:
    all_rows: list[pd.DataFrame] = []
    cache_count = 0
    errors: list[str] = []
    for ranking_name, slug in YAHOO_RANKINGS.items():
        for page in range(1, config.yahoo_pages + 1):
            url = (
                f"https://finance.yahoo.co.jp/stocks/ranking/{slug}"
                f"?market=all&page={page}"
            )
            cache_path = config.raw_dir / f"yahoo_{slug}_{page}.html"
            try:
                payload, cache_used = _read_or_fetch(
                    url, cache_path, config.request_timeout
                )
                cache_count += int(cache_used)
                html = payload.decode("utf-8", errors="replace")
                all_rows.append(parse_yahoo_ranking(html, ranking_name, page))
            except DataSourceError as exc:
                errors.append(str(exc))

    if not all_rows:
        detail = " / ".join(errors[:3])
        raise DataSourceError(f"Yahooランキングを取得できませんでした。{detail}")

    ranking_rows = pd.concat(all_rows, ignore_index=True)
    summary = (
        ranking_rows.groupby("code", as_index=False)
        .agg(
            yahoo_name=("yahoo_name", "first"),
            best_yahoo_rank=("rank", "min"),
            ranking_hits=("ranking", "nunique"),
            ranking_sources=("ranking", lambda values: "・".join(sorted(set(values)))),
        )
        .sort_values(
            ["ranking_hits", "best_yahoo_rank"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )
    snapshot_path = config.raw_dir / "yahoo_candidates.json"
    snapshot_path.write_text(
        json.dumps(summary.to_dict("records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary, {
        "source": "Yahoo!ファイナンス 日本株ランキング",
        "pages": len(all_rows),
        "cache_pages": cache_count,
        "count": int(len(summary)),
        "errors": errors,
    }


def build_candidate_pool(
    jpx: pd.DataFrame, yahoo: pd.DataFrame
) -> pd.DataFrame:
    pool = jpx.merge(yahoo, how="inner", on="code")
    pool["candidate_score"] = (
        pool["ranking_hits"] * 100
        + (151 - pool["best_yahoo_rank"].clip(upper=150))
    )
    pool = pool.sort_values(
        ["candidate_score", "best_yahoo_rank"], ascending=[False, True]
    )
    return pool.reset_index(drop=True)
