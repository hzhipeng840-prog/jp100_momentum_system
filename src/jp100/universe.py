from __future__ import annotations

import pandas as pd


UNIVERSE_LABELS = {
    "yahoo": "Yahooランキング",
    "jpx_liquidity": "JPX流動性",
}


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.fillna("").astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y"}
    )


def build_liquidity_universe(
    jpx: pd.DataFrame,
    features: pd.DataFrame,
    *,
    size: int,
    yahoo_codes: set[str] | None = None,
) -> pd.DataFrame:
    if jpx.empty or features.empty:
        return pd.DataFrame()
    universe = jpx.merge(features, how="inner", on="ticker")
    universe["avg_turnover_20d"] = pd.to_numeric(
        universe.get("avg_turnover_20d"),
        errors="coerce",
    )
    universe = universe[
        universe["avg_turnover_20d"].gt(0)
        & universe["return_20d"].notna()
        & universe["return_60d"].notna()
    ].copy()
    universe = universe.sort_values(
        ["avg_turnover_20d", "ticker"],
        ascending=[False, True],
    ).head(size)
    universe.insert(0, "liquidity_rank", range(1, len(universe) + 1))
    codes = yahoo_codes or set()
    universe["in_yahoo_pool"] = universe["code"].astype(str).isin(codes)
    universe["universe_source"] = "jpx_liquidity"
    universe["universe_label"] = UNIVERSE_LABELS["jpx_liquidity"]
    return universe.reset_index(drop=True)


def build_universe_observations(
    yahoo_top100: pd.DataFrame,
    liquidity_top100: pd.DataFrame,
    *,
    evaluation_version: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for source, frame in (
        ("yahoo", yahoo_top100),
        ("jpx_liquidity", liquidity_top100),
    ):
        if frame.empty:
            continue
        current = frame.copy()
        current["universe_source"] = source
        current["universe_label"] = UNIVERSE_LABELS[source]
        current["evaluation_version"] = evaluation_version
        frames.append(current)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_universe_comparison(
    followups: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    cost_bps: int = 10,
) -> pd.DataFrame:
    if followups.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for (version, source, label), group in followups.groupby(
        ["evaluation_version", "universe_source", "universe_label"],
        dropna=False,
    ):
        for day in horizons:
            settled_column = f"settled_{day}d"
            if settled_column not in group:
                continue
            settled = _truthy(group[settled_column])
            gross = pd.to_numeric(
                group.loc[settled, f"open_buy_return_{day}d"],
                errors="coerce",
            ).dropna()
            excess = pd.to_numeric(
                group.loc[settled, f"open_buy_excess_return_{day}d"],
                errors="coerce",
            ).dropna()
            net_column = f"net_open_buy_return_{day}d_{cost_bps}bps"
            net = pd.to_numeric(
                group.loc[settled, net_column],
                errors="coerce",
            ).dropna()
            rows.append(
                {
                    "evaluation_version": str(version),
                    "universe_source": str(source),
                    "universe_label": str(label),
                    "horizon": f"{day}d",
                    "sample_count": int(len(group)),
                    "valid_count": int(len(gross)),
                    "avg_open_buy_return": (
                        float(gross.mean()) if not gross.empty else None
                    ),
                    "median_open_buy_return": (
                        float(gross.median()) if not gross.empty else None
                    ),
                    "win_rate": (
                        float((gross > 0).mean()) if not gross.empty else None
                    ),
                    "avg_excess_return": (
                        float(excess.mean()) if not excess.empty else None
                    ),
                    "avg_net_return": (
                        float(net.mean()) if not net.empty else None
                    ),
                    "cost_bps_one_way": cost_bps,
                }
            )
    return pd.DataFrame(rows)


def build_version_comparison(
    evaluation_followups: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = (1, 3, 5, 10),
    cost_bps: int = 10,
) -> pd.DataFrame:
    if evaluation_followups.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for version, group in evaluation_followups.groupby(
        "evaluation_version",
        dropna=False,
    ):
        for day in horizons:
            settled_column = f"settled_{day}d"
            if settled_column not in group:
                continue
            settled = _truthy(group[settled_column])
            working = group.loc[settled].copy()
            gross = pd.to_numeric(
                working.get(f"open_buy_return_{day}d"),
                errors="coerce",
            ).dropna()
            excess = pd.to_numeric(
                working.get(f"open_buy_excess_return_{day}d"),
                errors="coerce",
            ).dropna()
            net = pd.to_numeric(
                working.get(f"net_open_buy_return_{day}d_{cost_bps}bps"),
                errors="coerce",
            ).dropna()
            top20 = working[
                pd.to_numeric(working.get("rank"), errors="coerce").le(20)
            ]
            top20_return = pd.to_numeric(
                top20.get(f"open_buy_return_{day}d"),
                errors="coerce",
            ).dropna()
            rows.append(
                {
                    "evaluation_version": str(version),
                    "horizon": f"{day}d",
                    "sample_count": int(len(group)),
                    "valid_count": int(len(gross)),
                    "avg_open_buy_return": (
                        float(gross.mean()) if not gross.empty else None
                    ),
                    "avg_excess_return": (
                        float(excess.mean()) if not excess.empty else None
                    ),
                    "avg_net_return": (
                        float(net.mean()) if not net.empty else None
                    ),
                    "win_rate": (
                        float((gross > 0).mean()) if not gross.empty else None
                    ),
                    "top20_avg_return": (
                        float(top20_return.mean())
                        if not top20_return.empty
                        else None
                    ),
                    "cost_bps_one_way": cost_bps,
                }
            )
    return pd.DataFrame(rows)
