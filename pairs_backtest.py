"""
pairs_backtest.py - 수정판 페어 트레이딩 백테스트 (2024-2 캡스톤 후속)

원본 노트북(capstone_test_1.ipynb)의 문제를 고친 독립 실행 스크립트.

수정 사항
  1. 스프레드 = log(Ticker2) - beta * log(Ticker1). beta는 형성 기간(formation) OLS로만 추정.
  2. 포지션 크기 = beta 가중 달러 노출, 페어당 총 명목 = capital. 주가 수준과 무관.
  3. 청산 = z-score가 0으로 복귀할 때(exit_z). 밴드 재진입 즉시 청산 아님.
  4. 일별 평가손익(mark-to-market) 기록 -> 수익률, 변동성, Sharpe, MDD, 시장 beta/alpha 계산.
  5. 벤치마크 = 3개월 T-bill(^IRX) 초과수익 + S&P 500(^GSPC)에 대한 alpha/beta 회귀.

정보 유출(look-ahead) 방지 규칙
  - 페어 선정과 beta 추정은 형성 기간 데이터만 사용. 거래 기간 데이터는 절대 보지 않음.
  - z-score의 이동평균/표준편차는 당일 종가까지의 과거 lookback일만 사용 (rolling).
  - 신호는 t일 종가에서 계산, 체결은 t+1일 시가. 같은 봉 안에서 신호와 체결을 함께 하지 않음.
  - 시계열 순서를 섞지 않음. 전 기간 통계(평균, 표준편차 등)를 미리 계산해 쓰지 않음.
  - 남아 있는 한계: 유니버스가 현재 시점의 S&P 500 구성 종목이라 생존 편향이 있음.
    yfinance는 상장폐지 종목을 제공하지 않아 완전히 제거할 수 없음. 결과 해석 시 명시할 것.

사용법
  python pairs_backtest.py h1        # 보고서의 50개 페어, 2023 형성 / 2024 상반기 거래
  python pairs_backtest.py rolling   # 2014~2024 전 구간: 12개월 형성 / 6개월 거래 롤링
  옵션: --lookback 30 --entry 2 --exit 0 --capital 10000 --cost-bps 5
"""
import argparse
import itertools
import os
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "results_v2")
TRADING_DAYS = 252


# ----------------------------------------------------------------------------
# 데이터
# ----------------------------------------------------------------------------
def load_universe() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(ROOT, "csv", "snp500.csv"))
    df = df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    return df


def load_prices(tickers, start, end, cache_name):
    """auto_adjust=True: 분할/배당 조정 OHLC. 롱숏 손익에는 총수익 가격이 맞음.
    반환: (open, close) 와이드 DataFrame. 캐시는 data/ 아래 pickle."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, cache_name)
    if os.path.exists(path):
        d = pd.read_pickle(path)
        return d["open"], d["close"]
    import yfinance as yf
    print(f"[download] {len(tickers)} tickers {start} ~ {end}")
    raw = yf.download(list(tickers), start=start, end=end, auto_adjust=True,
                      group_by="column", threads=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        open_, close = raw["Open"], raw["Close"]
    else:  # 단일 티커
        open_, close = raw[["Open"]], raw[["Close"]]
        open_.columns = close.columns = list(tickers)
    open_ = open_.sort_index().dropna(how="all")
    close = close.sort_index().dropna(how="all")
    open_.index = pd.to_datetime(open_.index).tz_localize(None)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    pd.to_pickle({"open": open_, "close": close}, path)
    return open_, close


def load_single(symbol, start, end, cache_name) -> pd.Series:
    _, close = load_prices([symbol], start, end, cache_name)
    return close.iloc[:, 0].rename(symbol)


def daily_risk_free(irx: pd.Series, index) -> pd.Series:
    """^IRX = 13주 T-bill 연율 수익률(%). 일별로 환산해 거래일 인덱스에 맞춤."""
    rf = (irx / 100.0 / TRADING_DAYS).reindex(index).ffill().bfill()
    return rf.rename("rf")


# ----------------------------------------------------------------------------
# 페어 선정 (형성 기간 데이터만 사용)
# ----------------------------------------------------------------------------
def fit_pair(log_x: pd.Series, log_y: pd.Series):
    """log_y = alpha + beta * log_x + e. Engle-Granger 1단계 + 잔차 ADF."""
    X = sm.add_constant(log_x.values)
    res = sm.OLS(log_y.values, X).fit()
    alpha, beta = res.params
    resid = pd.Series(res.resid, index=log_y.index)
    pval = adfuller(resid.values, autolag="AIC")[1]
    return alpha, beta, pval, resid.std()


def select_pairs(close, universe, f_start, f_end, p_thresh=0.05, min_obs=200):
    """산업군(GICS Sub-Industry)별로 ADF p<p_thresh 중 잔차 표준편차가 가장 낮은 페어 1개.
    원본 규칙과 같되 log 가격을 써서 주가 수준에 영향받지 않게 함. beta>0만 허용."""
    logp = np.log(close.loc[f_start:f_end])
    rows = []
    for sub, grp in universe.groupby("GICS Sub-Industry"):
        tick = [t for t in grp["Symbol"] if t in logp.columns and logp[t].notna().sum() >= min_obs]
        if len(tick) < 2:
            continue
        best = None
        for a, b in itertools.combinations(tick, 2):
            both = logp[[a, b]].dropna()
            if len(both) < min_obs:
                continue
            alpha, beta, pval, rstd = fit_pair(both[a], both[b])
            if pval < p_thresh and beta > 0 and (best is None or rstd < best["resid_std"]):
                best = dict(Sector=grp["GICS Sector"].iloc[0], SubIndustry=sub,
                            Ticker1=a, Ticker2=b, alpha=alpha, beta=beta, p_value=pval, resid_std=rstd)
        if best:
            rows.append(best)
    return pd.DataFrame(rows)


def patch_local(open_, close, ticker):
    """yfinance에서 사라진 종목(상폐/티커 변경)을 저장소의 로컬 CSV로 보완.
    csv/{t}.csv = 2023 형성 기간, backtest_csv/{t}_backtest.csv = 2024 상반기.
    둘 다 수정주가(Adj Close) 기준으로 맞추고 시가는 Adj/Close 비율로 조정."""
    frames = []
    for path in (os.path.join(ROOT, "csv", f"{ticker}.csv"),
                 os.path.join(ROOT, "backtest_csv", f"{ticker}_backtest.csv")):
        if os.path.exists(path):
            d = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
            frames.append(pd.DataFrame({"close": d["Adj Close"], "open": d["Open"] * d["Adj Close"] / d["Close"]}))
    if not frames:
        return open_, close
    loc = pd.concat(frames).sort_index()
    loc = loc[~loc.index.duplicated()]
    open_ = open_.copy(); close = close.copy()
    for col, src in (("open", open_), ("close", close)):
        s = src[ticker] if ticker in src.columns else pd.Series(np.nan, index=src.index)
        s = s.reindex(src.index.union(loc.index))
        s = s.fillna(loc[col].reindex(s.index))
        src[ticker] = s.reindex(src.index)
    print(f"[patch] {ticker}: {loc.index.min():%Y-%m-%d} ~ {loc.index.max():%Y-%m-%d} from local csv")
    return open_, close


def report_pairs_with_beta(close, f_start, f_end, min_obs=200):
    """보고서의 50개 페어(csv/stable_pairs.csv)를 그대로 쓰되 beta를 형성 기간 log 가격으로 재추정.
    형성 기간 데이터를 구할 수 없는 페어(상폐 등)는 제외하고 출력."""
    sp = pd.read_csv(os.path.join(ROOT, "csv", "stable_pairs.csv"))
    logp = np.log(close.loc[f_start:f_end])
    rows, dropped = [], []
    for _, r in sp.iterrows():
        a, b = r["Ticker 1"], r["Ticker 2"]
        both = logp[[a, b]].dropna() if a in logp.columns and b in logp.columns else pd.DataFrame()
        if len(both) < min_obs:
            dropped.append(f"{a}-{b}")
            continue
        alpha, beta, pval, rstd = fit_pair(both[a], both[b])
        rows.append(dict(Sector=r["Sector"], SubIndustry=r["Industry Group"], Ticker1=a, Ticker2=b,
                         alpha=alpha, beta=beta, p_value=pval, resid_std=rstd))
    if dropped:
        print(f"[drop] 형성 기간 데이터 없음 (상폐/티커 변경): {dropped}")
    return pd.DataFrame(rows)


def apply_sizing(pairs: pd.DataFrame, sizing: str) -> pd.DataFrame:
    """beta 모드: 형성 기간 OLS beta 사용, beta<=0 페어는 롱숏 페어가 아니므로 제외.
    dollar 모드: beta=1 (스프레드 = log y - log x, 1:1 달러 중립). Gatev et al.(2006) 방식에 가까움."""
    pairs = pairs.copy()
    if sizing == "dollar":
        pairs["beta_ols"] = pairs["beta"]
        pairs["beta"] = 1.0
        return pairs
    bad = pairs[pairs["beta"] <= 0]
    if len(bad):
        print(f"[drop] beta<=0 (같은 방향으로 움직이지 않아 롱숏 페어 불성립): "
              f"{[f'{a}-{b} ({x:.2f})' for a, b, x in zip(bad.Ticker1, bad.Ticker2, bad.beta)]}")
    return pairs[pairs["beta"] > 0]


# ----------------------------------------------------------------------------
# 거래 엔진 (페어 1개)
# ----------------------------------------------------------------------------
def backtest_pair(open_, close, t1, t2, beta, t_start, t_end,
                  lookback=30, entry_z=2.0, exit_z=0.0, capital=10_000.0, cost_bps=5.0, stop_z=0.0):
    """신호: t일 종가 z-score. 체결: t+1일 시가. 일별 평가손익(달러) 반환.
    방향 +1 = 롱 스프레드 (롱 t2, 숏 t1), -1 = 숏 스프레드."""
    px = close[[t1, t2]].dropna()
    px = px.loc[:t_end]
    op = open_[[t1, t2]].reindex(px.index)
    op = op.where(op.notna(), px)  # 시가 결측이면 종가로 대체

    spread = np.log(px[t2]) - beta * np.log(px[t1])
    mu = spread.rolling(lookback).mean()
    sd = spread.rolling(lookback).std()
    z = ((spread - mu) / sd)

    dates = px.index[(px.index >= pd.Timestamp(t_start)) & (px.index <= pd.Timestamp(t_end))]
    if len(dates) == 0:
        return None, None
    loc0 = px.index.get_loc(dates[0])
    if loc0 == 0:
        return None, None

    c1, c2 = px[t1].values, px[t2].values
    o1, o2 = op[t1].values, op[t2].values
    zv = z.values

    pos, sh1, sh2 = 0, 0.0, 0.0
    pending = None  # ("enter", dir) | "exit"
    entry_date = entry_i = None
    trade_pnl = 0.0
    gross = np.zeros(len(dates))
    cost = np.zeros(len(dates))
    trades = []
    w_y, w_x = 1.0 / (1.0 + beta), beta / (1.0 + beta)  # beta 가중 달러 배분

    for k, d in enumerate(dates):
        i = loc0 + k
        pnl = 0.0
        if pending == "exit":
            pnl += sh1 * (o1[i] - c1[i - 1]) + sh2 * (o2[i] - c2[i - 1])
            fee = (abs(sh1) * o1[i] + abs(sh2) * o2[i]) * cost_bps / 1e4
            cost[k] += fee
            trades.append(dict(entry=entry_date, exit=d, dir=pos, days=i - entry_i,
                               pnl=trade_pnl + pnl - fee))
            pos, sh1, sh2 = 0, 0.0, 0.0
        elif pending is not None and pending[0] == "enter":
            dir_ = pending[1]
            sh2 = dir_ * capital * w_y / o2[i]
            sh1 = -dir_ * capital * w_x / o1[i]
            fee = capital * cost_bps / 1e4
            cost[k] += fee
            pos, entry_date, entry_i, trade_pnl = dir_, d, i, -fee
            pnl += sh1 * (c1[i] - o1[i]) + sh2 * (c2[i] - o2[i])
            trade_pnl += pnl
        elif pos != 0:
            pnl += sh1 * (c1[i] - c1[i - 1]) + sh2 * (c2[i] - c2[i - 1])
            trade_pnl += pnl
        gross[k] += pnl
        pending = None

        # 마지막 거래일: 종가로 강제 청산 (평가손익은 이미 반영, 비용만 추가)
        if k == len(dates) - 1:
            if pos != 0:
                fee = (abs(sh1) * c1[i] + abs(sh2) * c2[i]) * cost_bps / 1e4
                cost[k] += fee
                trades.append(dict(entry=entry_date, exit=d, dir=pos, days=i - entry_i,
                                   pnl=trade_pnl - fee, forced=True))
            break

        # 당일 종가 신호 -> 다음 날 시가 체결
        zt = zv[i]
        if np.isnan(zt):
            continue
        if pos == 0:
            if zt > entry_z:
                pending = ("enter", -1)
            elif zt < -entry_z:
                pending = ("enter", +1)
        else:
            if (pos == -1 and zt <= exit_z) or (pos == +1 and zt >= -exit_z):
                pending = "exit"
            elif stop_z > 0 and abs(zt) > stop_z:  # 손절: 스프레드가 더 벌어지면 청산
                pending = "exit"

    pnl_df = pd.DataFrame({"gross": gross, "cost": cost}, index=dates)
    return pnl_df, pd.DataFrame(trades)


def run_period(open_, close, pairs, t_start, t_end, p):
    """페어 전부 실행. 반환: 페어별 통계, 일별 손익 행렬(gross, cost), 활성 페어 수."""
    stats, gross_cols, cost_cols, active_cols = [], {}, {}, {}
    for _, r in pairs.iterrows():
        name = f"{r.Ticker1}-{r.Ticker2}"
        pnl_df, trades = backtest_pair(open_, close, r.Ticker1, r.Ticker2, r.beta, t_start, t_end,
                                       p.lookback, p.entry, p.exit, p.capital, p.cost_bps, p.stop_z)
        if pnl_df is None:
            continue
        gross_cols[name] = pnl_df["gross"]
        cost_cols[name] = pnl_df["cost"]
        net = pnl_df["gross"] - pnl_df["cost"]
        ntr = len(trades)
        stats.append(dict(
            Pair=name, Sector=r.Sector, SubIndustry=r.SubIndustry, beta=round(r.beta, 3),
            adf_p=round(r.p_value, 4), Trades=ntr,
            WinRate=round((trades.pnl > 0).mean(), 3) if ntr else np.nan,
            AvgHoldDays=round(trades.days.mean(), 1) if ntr else np.nan,
            GrossPnL=round(pnl_df["gross"].sum(), 2), NetPnL=round(net.sum(), 2),
            NetReturnPct=round(net.sum() / p.capital * 100, 3),
            ForcedClose=int(trades.get("forced", pd.Series(dtype=bool)).fillna(False).sum()) if ntr else 0,
        ))
    gross_m = pd.DataFrame(gross_cols)
    cost_m = pd.DataFrame(cost_cols)
    return pd.DataFrame(stats), gross_m, cost_m


# ----------------------------------------------------------------------------
# 성과 지표
# ----------------------------------------------------------------------------
def max_drawdown(total_ret: pd.Series) -> float:
    eq = (1 + total_ret).cumprod()
    return float((eq / eq.cummax() - 1).min())


def perf(total_ret: pd.Series, rf: pd.Series, mkt_ret: pd.Series) -> dict:
    """total_ret: 전략 일별 총수익률(현금 T-bill 이자 포함). mkt_ret: 시장 일별 수익률."""
    ex = (total_ret - rf).dropna()
    mex = (mkt_ret - rf).reindex(ex.index).dropna()
    ex = ex.reindex(mex.index)
    n = len(ex)
    out = dict(
        Days=n,
        TotalReturnPct=round(((1 + total_ret).prod() - 1) * 100, 2),
        RfReturnPct=round(((1 + rf).prod() - 1) * 100, 2),
        ExcessReturnPct=round(ex.sum() * 100, 2),
        AnnReturnPct=round(((1 + total_ret).prod() ** (TRADING_DAYS / n) - 1) * 100, 2),
        AnnVolPct=round(ex.std() * np.sqrt(TRADING_DAYS) * 100, 2),
        Sharpe=round(ex.mean() / ex.std() * np.sqrt(TRADING_DAYS), 2) if ex.std() > 0 else np.nan,
        MaxDrawdownPct=round(max_drawdown(total_ret) * 100, 2),
    )
    if n > 10:
        X = sm.add_constant(mex.values)
        res = sm.OLS(ex.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        out.update(Beta=round(res.params[1], 3), Beta_t=round(res.tvalues[1], 2),
                   AlphaAnnPct=round(res.params[0] * TRADING_DAYS * 100, 2), Alpha_t=round(res.tvalues[0], 2))
    return out


def portfolio_returns(gross_m, cost_m, capital, rf):
    """committed: 선정된 모든 페어에 capital 배정. fully-invested: 그날 포지션 있는 페어 자본만."""
    net = gross_m - cost_m
    n_pairs = gross_m.shape[1]
    active = (gross_m != 0).sum(axis=1).replace(0, np.nan)
    committed_ex = net.sum(axis=1) / (n_pairs * capital)
    committed_gross_ex = gross_m.sum(axis=1) / (n_pairs * capital)
    invested_ex = (net.sum(axis=1) / (active * capital)).fillna(0.0)
    rf_ = rf.reindex(net.index)
    return pd.DataFrame({
        "strat_excess_net": committed_ex, "strat_total_net": committed_ex + rf_,
        "strat_excess_gross": committed_gross_ex, "strat_total_gross": committed_gross_ex + rf_,
        "strat_total_invested": invested_ex + rf_, "active_pairs": active.fillna(0).astype(int),
    })


def plot_equity(daily, mkt, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6))
    idx = daily.index
    ax.plot(idx, (1 + daily["strat_total_net"]).cumprod(), label="Pairs strategy (net of costs, incl. T-bill)")
    ax.plot(idx, (1 + daily["strat_total_gross"]).cumprod(), label="Pairs strategy (gross)", alpha=0.6)
    ax.plot(idx, (1 + daily["rf"]).cumprod(), label="3M T-bill", linestyle="--")
    ax.plot(idx, (1 + mkt.reindex(idx).fillna(0)).cumprod(), label="S&P 500 (^GSPC)", alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Growth of $1")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_summary(path, title, blocks):
    lines = [f"# {title}", ""]
    for head, d in blocks:
        lines += [f"## {head}", "", "| 지표 | 값 |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in d.items()]
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


# ----------------------------------------------------------------------------
# 모드
# ----------------------------------------------------------------------------
def mode_h1(p):
    f_start, f_end = "2023-01-01", "2023-12-31"
    t_start, t_end = "2024-01-01", "2024-06-30"
    uni = load_universe()
    sp = pd.read_csv(os.path.join(ROOT, "csv", "stable_pairs.csv"))
    tickers = sorted(set(sp["Ticker 1"]) | set(sp["Ticker 2"]))
    open_, close = load_prices(tickers, "2022-11-01", "2024-07-01", "prices_h1_2024.pkl")
    missing = [t for t in tickers if t not in close.columns or close[t].loc[f_start:f_end].notna().sum() < 120]
    for t in missing:
        open_, close = patch_local(open_, close, t)
    gspc = load_single("^GSPC", "2022-11-01", "2024-07-01", "gspc_h1.pkl")
    irx = load_single("^IRX", "2022-11-01", "2024-07-01", "irx_h1.pkl")

    pairs = apply_sizing(report_pairs_with_beta(close, f_start, f_end, min_obs=120), p.sizing)
    stats, gross_m, cost_m = run_period(open_, close, pairs, t_start, t_end, p)
    rf = daily_risk_free(irx, gross_m.index)
    daily = portfolio_returns(gross_m, cost_m, p.capital, rf)
    daily["rf"] = rf
    mkt = gspc.pct_change().reindex(daily.index)
    daily["mkt"] = mkt

    os.makedirs(OUT_DIR, exist_ok=True)
    pre = f"h1_2024{p.tag}"
    stats.sort_values("NetReturnPct", ascending=False).to_csv(os.path.join(OUT_DIR, f"{pre}_pairs.csv"), index=False)
    daily.to_csv(os.path.join(OUT_DIR, f"{pre}_daily.csv"))
    plot_equity(daily, mkt, f"Pairs trading vs benchmarks, 2024-01 ~ 2024-06 ({len(stats)} report pairs){p.tag}",
                os.path.join(OUT_DIR, f"{pre}_equity.png"))

    blocks = [
        ("전략 (비용 차감, committed capital 기준)", perf(daily["strat_total_net"], rf, mkt)),
        ("전략 (비용 미차감)", perf(daily["strat_total_gross"], rf, mkt)),
        ("전략 (fully-invested 자본 기준, 비용 차감)", perf(daily["strat_total_invested"], rf, mkt)),
        ("S&P 500 (^GSPC, 가격지수)", {k: v for k, v in perf(mkt.fillna(0), rf, mkt).items() if not k.startswith(("Beta", "Alpha"))}),
        ("거래 요약", dict(
            Pairs=len(stats), TotalTrades=int(stats.Trades.sum()),
            AvgTradesPerPair=round(stats.Trades.mean(), 1),
            WinRate=round((stats.WinRate * stats.Trades).sum() / stats.Trades.sum(), 3),
            AvgHoldDays=round((stats.AvgHoldDays * stats.Trades).sum() / stats.Trades.sum(), 1),
            PairsPositive=int((stats.NetPnL > 0).sum()), ForcedCloses=int(stats.ForcedClose.sum()),
            BestPair=f"{stats.loc[stats.NetReturnPct.idxmax(), 'Pair']} {stats.NetReturnPct.max()}%",
            WorstPair=f"{stats.loc[stats.NetReturnPct.idxmin(), 'Pair']} {stats.NetReturnPct.min()}%",
            Params=f"sizing={p.sizing} lookback={p.lookback} entry={p.entry} exit={p.exit} stop_z={p.stop_z} cost={p.cost_bps}bps capital={p.capital}",
        )),
    ]
    write_summary(os.path.join(OUT_DIR, f"{pre}_summary.md"), f"2024 상반기 수정판 백테스트 요약{p.tag}", blocks)


def mode_rolling(p):
    uni = load_universe()
    tickers = uni["Symbol"].tolist()
    open_, close = load_prices(tickers, "2013-10-01", "2025-01-01", "prices_2013_2024.pkl")
    gspc = load_single("^GSPC", "2013-10-01", "2025-01-01", "gspc_long.pkl")
    irx = load_single("^IRX", "2013-10-01", "2025-01-01", "irx_long.pkl")

    starts = pd.date_range(f"{p.rolling_start}-01-01", f"{p.rolling_end}-07-01", freq="6MS")
    all_stats, gross_parts, cost_parts, period_rows, all_pairs = [], [], [], [], []
    os.makedirs(OUT_DIR, exist_ok=True)
    for ts in starts:
        f_start = ts - pd.DateOffset(years=1)
        f_end = ts - pd.Timedelta(days=1)
        t_end = ts + pd.DateOffset(months=6) - pd.Timedelta(days=1)
        label = f"{ts:%Y-%m}~{t_end:%Y-%m}"
        pairs = select_pairs(close, uni, f_start, f_end, p.p_thresh)
        if pairs.empty:
            print(f"[{label}] no pairs"); continue
        pairs["Period"] = label
        all_pairs.append(pairs)
        pairs = apply_sizing(pairs, p.sizing)
        stats, gross_m, cost_m = run_period(open_, close, pairs, ts, t_end, p)
        stats["Period"] = label
        all_stats.append(stats)
        rf = daily_risk_free(irx, gross_m.index)
        d = portfolio_returns(gross_m, cost_m, p.capital, rf)
        d["rf"] = rf
        d["mkt"] = gspc.pct_change().reindex(d.index)
        gross_parts.append(d)
        pf = perf(d["strat_total_net"], rf, d["mkt"])
        pm = perf(d["mkt"].fillna(0), rf, d["mkt"])
        period_rows.append(dict(Period=label, Pairs=len(stats), Trades=int(stats.Trades.sum()),
                                StratTotalPct=pf["TotalReturnPct"], StratExcessPct=pf["ExcessReturnPct"],
                                StratSharpe=pf["Sharpe"], StratMDDPct=pf["MaxDrawdownPct"],
                                Beta=pf.get("Beta"), AlphaAnnPct=pf.get("AlphaAnnPct"),
                                RfPct=pf["RfReturnPct"], MktTotalPct=pm["TotalReturnPct"], MktMDDPct=pm["MaxDrawdownPct"]))
        print(f"[{label}] pairs={len(stats):3d} strat={pf['TotalReturnPct']:6.2f}% rf={pf['RfReturnPct']:5.2f}% "
              f"mkt={pm['TotalReturnPct']:6.2f}% beta={pf.get('Beta')}")

    daily = pd.concat(gross_parts).sort_index()
    daily = daily[~daily.index.duplicated(keep="first")]
    pd.concat(all_stats).to_csv(os.path.join(OUT_DIR, "rolling_pairs.csv"), index=False)
    pd.concat(all_pairs).to_csv(os.path.join(OUT_DIR, "rolling_selected_pairs.csv"), index=False)
    periods = pd.DataFrame(period_rows)
    periods.to_csv(os.path.join(OUT_DIR, "rolling_periods.csv"), index=False)
    daily.to_csv(os.path.join(OUT_DIR, "rolling_daily.csv"))
    plot_equity(daily, daily["mkt"], f"Pairs trading vs benchmarks, {p.rolling_start}~{p.rolling_end} (12m formation / 6m trading)",
                os.path.join(OUT_DIR, "rolling_equity.png"))

    rf = daily["rf"]
    blocks = [
        ("전략 전 기간 (비용 차감, committed capital)", perf(daily["strat_total_net"], rf, daily["mkt"])),
        ("전략 전 기간 (비용 미차감)", perf(daily["strat_total_gross"], rf, daily["mkt"])),
        ("S&P 500 전 기간", {k: v for k, v in perf(daily["mkt"].fillna(0), rf, daily["mkt"]).items() if not k.startswith(("Beta", "Alpha"))}),
        ("기간별 요약", dict(
            Periods=len(periods), PeriodsStratBeatsRf=int((periods.StratExcessPct > 0).sum()),
            PeriodsStratBeatsMkt=int((periods.StratTotalPct > periods.MktTotalPct).sum()),
            MedianPairsPerPeriod=int(periods.Pairs.median()),
            Params=f"sizing={p.sizing} lookback={p.lookback} entry={p.entry} exit={p.exit} stop_z={p.stop_z} cost={p.cost_bps}bps p<{p.p_thresh}",
        )),
    ]
    write_summary(os.path.join(OUT_DIR, "rolling_summary.md"),
                  f"롤링 백테스트 요약 {p.rolling_start}~{p.rolling_end}", blocks)
    print(periods.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["h1", "rolling"])
    ap.add_argument("--lookback", type=int, default=30)
    ap.add_argument("--entry", type=float, default=2.0)
    ap.add_argument("--exit", type=float, default=0.0)
    ap.add_argument("--capital", type=float, default=10_000)
    ap.add_argument("--cost-bps", dest="cost_bps", type=float, default=5.0, help="편도 거래비용 bp (명목 기준)")
    ap.add_argument("--sizing", choices=["beta", "dollar"], default="beta",
                    help="beta: OLS beta 가중(beta<=0 제외), dollar: 1:1 달러 중립(beta=1)")
    ap.add_argument("--stop-z", dest="stop_z", type=float, default=0.0, help="손절 z-score (0=없음)")
    ap.add_argument("--tag", default="", help="출력 파일 접미사 (민감도 분석용)")
    ap.add_argument("--p-thresh", dest="p_thresh", type=float, default=0.05)
    ap.add_argument("--rolling-start", dest="rolling_start", type=int, default=2015)
    ap.add_argument("--rolling-end", dest="rolling_end", type=int, default=2024)
    p = ap.parse_args()
    if p.mode == "h1":
        mode_h1(p)
    else:
        mode_rolling(p)


if __name__ == "__main__":
    main()
