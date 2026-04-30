"""
投資手法 完全検証エンジン v1.0
全30+パターンをOOS検証してランキング化
"""

import os, json, warnings, time
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from scipy import stats
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

load_dotenv('/Users/mr.k/projects/and-ai-brain/.env')

FRED_KEY   = os.environ.get("FRED_API_KEY", "a01800eaced4b9d66ccda8b355b593db")
BOT_TOKEN  = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID    = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
OUT_FILE   = '/Users/mr.k/projects/and-ai-brain/full_strategy_results.json'

# ============================================================
# ユーティリティ
# ============================================================

def tg(text: str):
    """Telegram送信"""
    if not BOT_TOKEN:
        print("[TG skip] no token")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"[TG error] {e}")


def get_fred(series_id: str, limit: int = 1000) -> pd.Series:
    """FRED REST API から系列データを取得"""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "limit": limit,
        "sort_order": "asc",
    }
    r = requests.get(url, params=params, timeout=15)
    data = r.json().get("observations", [])
    s = pd.Series(
        {d["date"]: float(d["value"]) for d in data if d["value"] != "."},
        dtype=float
    )
    s.index = pd.to_datetime(s.index)
    return s


def get_prices(ticker: str, period: str = "5y") -> pd.Series:
    """
    OpenBBを優先してOHLCVデータを取得。失敗時はyfinanceにフォールバック。
    - OpenBBは長期データ（5年+）が制限なしで取得可能
    - tickerマッピング: BTC-USD → BTC-USD, ETH-USD → ETH-USD
    """
    from datetime import datetime, timedelta

    # period文字列を日付に変換
    period_map = {"1y": 365, "2y": 730, "3y": 1095, "5y": 1825, "10y": 3650}
    days = period_map.get(period, 1825)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # OpenBBで取得試行
    try:
        from openbb import obb
        # 暗号資産の場合
        if any(c in ticker for c in ["BTC", "ETH", "SOL", "XRP"]):
            result = obb.crypto.price.historical(
                symbol=ticker,
                start_date=start_date,
                provider="yfinance"
            )
        else:
            result = obb.equity.price.historical(
                symbol=ticker,
                start_date=start_date,
                provider="yfinance"
            )
        df = result.to_dataframe()
        df.index = pd.to_datetime(df.index)
        return df["close"].dropna().squeeze()
    except Exception as e:
        # フォールバック: yfinance直接
        import yfinance as yf
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        return df["Close"].dropna().squeeze()


# ============================================================
# バックテスト共通エンジン
# ============================================================

def backtest(prices: pd.Series, signals: pd.Series,
             lev: float = 2.0, stop: float = -0.08,
             hold_days: int = 30, take_profit: float = None) -> dict:
    """
    signals: +1=ロング、-1=ショート、0=ノーポジ
    OOS = 直近30%
    """
    prices  = prices.dropna()
    signals = signals.reindex(prices.index).fillna(0)

    if len(prices) < 10:
        empty = {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                 "win_rate": 0.0, "trades": 0, "pvalue": 1.0}
        return {"IS": empty, "OOS": empty}

    split   = max(int(len(prices) * 0.7), 1)
    oos_p   = prices.iloc[split:]
    oos_s   = signals.iloc[split:]

    def _run(p: pd.Series, s: pd.Series) -> dict:
        capital = 1.0
        equity  = []
        trades, wins = 0, 0
        pos = 0
        entry_price = 0.0
        hold = 0

        for i in range(len(p)):
            price = float(p.iloc[i])
            sig   = float(s.iloc[i])

            # ストップロス or ホールド期限 or 利確
            if pos != 0:
                ret = (price - entry_price) / entry_price * pos * lev
                hold += 1
                tp_hit = take_profit is not None and ret >= take_profit
                if ret <= stop or hold >= hold_days or tp_hit:
                    capital *= (1 + ret)
                    if ret > 0: wins += 1
                    trades += 1
                    pos = 0

            # 新規エントリー
            if pos == 0 and sig != 0:
                pos = int(sig)
                entry_price = price
                hold = 0

            equity.append(capital)

        # 未決済ポジション決済
        if pos != 0:
            ret = (float(p.iloc[-1]) - entry_price) / entry_price * pos * lev
            capital *= (1 + ret)
            if ret > 0: wins += 1
            trades += 1

        equity = np.array(equity)
        if len(equity) == 0:
            return {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                    "win_rate": 0.0, "trades": 0, "pvalue": 1.0}
        rets   = np.diff(equity) / (equity[:-1] + 1e-9)

        sharpe = float(np.mean(rets) / (np.std(rets) + 1e-9) * np.sqrt(252)) if len(rets) > 1 else 0.0
        peak   = np.maximum.accumulate(equity)
        mdd    = float(np.min(equity / (peak + 1e-9) - 1)) if len(equity) > 0 else 0.0
        win_r  = wins / max(trades, 1) * 100
        total  = float(capital - 1.0)

        # t検定 (p値)
        pval = 1.0
        if len(rets) > 5:
            t, pval = stats.ttest_1samp(rets, 0)
            pval = float(pval)

        return {
            "sharpe": round(sharpe, 3),
            "total_return": round(total * 100, 1),
            "mdd": round(mdd * 100, 1),
            "win_rate": round(win_r, 1),
            "trades": trades,
            "pvalue": round(pval, 4),
        }

    is_res  = _run(prices.iloc[:split], signals.iloc[:split])
    oos_res = _run(oos_p, oos_s)

    return {"IS": is_res, "OOS": oos_res}


# ============================================================
# A. テクニカル系
# ============================================================

def strategy_A1_macd(prices: pd.Series) -> pd.Series:
    """A1: MACD クロスオーバー (12,26,9)"""
    ema12  = prices.ewm(span=12).mean()
    ema26  = prices.ewm(span=26).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[macd > signal] = 1
    sig[macd < signal] = -1
    return sig


def strategy_A2_vol_breakout(prices: pd.Series, vol: pd.Series) -> pd.Series:
    """A2: 出来高急増 + 価格ブレイクアウト (vol 3倍 + 20日高値更新)"""
    vol_ma  = vol.rolling(20).mean()
    hi20    = prices.rolling(20).max().shift(1)
    cond    = (vol > vol_ma * 3) & (prices > hi20)
    sig     = pd.Series(0, index=prices.index, dtype=float)
    sig[cond] = 1
    return sig


def strategy_A3_golden_cross(prices: pd.Series) -> pd.Series:
    """A3: ゴールデンクロス (50MA > 200MA)"""
    ma50  = prices.rolling(50).mean()
    ma200 = prices.rolling(200).mean()
    sig   = pd.Series(0, index=prices.index, dtype=float)
    sig[ma50 > ma200] = 1
    sig[ma50 < ma200] = -1
    return sig


def strategy_A4_bb_squeeze(prices: pd.Series) -> pd.Series:
    """A4: ボリンジャースクイーズ (バンド幅が20日最小 → 拡大)"""
    ma   = prices.rolling(20).mean()
    std  = prices.rolling(20).std()
    bw   = (std * 2) / ma
    min_bw = bw.rolling(20).min()
    # スクイーズ解放: 現在バンド幅が直近最小から拡大
    expand = bw > min_bw * 1.05
    # 価格がMA上なら買い
    sig  = pd.Series(0, index=prices.index, dtype=float)
    sig[expand & (prices > ma)] = 1
    sig[expand & (prices < ma)] = -1
    return sig


def strategy_A5_weekly_z(prices: pd.Series) -> pd.Series:
    """A5: 週足Z値 (週足200MA乖離) — 乖離が大きすぎる時に逆張り"""
    weekly = prices.resample("W").last()
    ma200w = weekly.rolling(200).mean()
    std200w = weekly.rolling(200).std()
    z = (weekly - ma200w) / (std200w + 1e-9)
    z_daily = z.reindex(prices.index, method="ffill")
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[z_daily < -2] = 1   # 割安: 買い
    sig[z_daily > 2]  = -1  # 割高: 売り
    return sig


def strategy_A6_monthly_rsi(prices: pd.Series) -> pd.Series:
    """A6: 月足逆張り (月足RSI < 30)"""
    monthly = prices.resample("ME").last()
    delta = monthly.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = 100 - 100 / (1 + rs)
    rsi_d = rsi.reindex(prices.index, method="ffill")
    sig   = pd.Series(0, index=prices.index, dtype=float)
    sig[rsi_d < 30] = 1
    sig[rsi_d > 70] = -1
    return sig


# ============================================================
# B. ファンダメンタル系
# ============================================================

def strategy_B1_nvt(prices: pd.Series, coingecko_vol: pd.Series = None) -> pd.Series:
    """B1: NVT < 30 (時価総額/出来高)"""
    # yfinanceの出来高を代替利用
    sig = pd.Series(0, index=prices.index, dtype=float)
    if coingecko_vol is None:
        return sig
    nvt = prices / (coingecko_vol + 1e-9)
    nvt_norm = (nvt - nvt.rolling(365).mean()) / (nvt.rolling(365).std() + 1e-9)
    sig[nvt_norm < -1] = 1   # NVT低め → 割安
    sig[nvt_norm > 1]  = -1
    return sig


def strategy_B2_halving(prices: pd.Series) -> pd.Series:
    """B2: 半減期後サイクル (2024-04-19以降 365日保有)"""
    halving_date = pd.Timestamp("2024-04-19")
    sig = pd.Series(0, index=prices.index, dtype=float)
    end_date = halving_date + timedelta(days=365)
    mask = (prices.index >= halving_date) & (prices.index <= end_date)
    sig[mask] = 1
    return sig


def strategy_B3_btc_dom(prices_eth: pd.Series, btc_dom: pd.Series) -> pd.Series:
    """B3: BTC支配率ピーク後アルト (BTC dominance > 60% → ETH買い)"""
    dom_d = btc_dom.reindex(prices_eth.index, method="ffill")
    sig   = pd.Series(0, index=prices_eth.index, dtype=float)
    sig[dom_d > 60] = 1
    return sig


# ============================================================
# C. マクロ系
# ============================================================

def strategy_C1_yield_curve(prices: pd.Series) -> pd.Series:
    """C1: 逆イールドカーブ解消 (T10Y2Y: マイナス→プラス転換)"""
    print("  [C1] FRED T10Y2Y 取得中...")
    try:
        t10y2y = get_fred("T10Y2Y")
        t_d    = t10y2y.reindex(prices.index, method="ffill")
        # マイナス→プラス転換 (クロス)
        sig = pd.Series(0, index=prices.index, dtype=float)
        was_neg = t_d.shift(1) < 0
        is_pos  = t_d >= 0
        sig[was_neg & is_pos] = 1  # 転換点で買い
        return sig
    except Exception as e:
        print(f"  [C1 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_C2_m2(prices: pd.Series) -> pd.Series:
    """C2: M2増加率 > 5% YoY"""
    print("  [C2] FRED M2 取得中...")
    try:
        m2 = get_fred("MABMM301USM189S")
        m2_yoy = m2.pct_change(12) * 100
        m2_d   = m2_yoy.reindex(prices.index, method="ffill")
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[m2_d > 5] = 1
        return sig
    except Exception as e:
        print(f"  [C2 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_C3_dxy(prices: pd.Series) -> pd.Series:
    """C3: DXY下落トレンド"""
    print("  [C3] DXY 取得中...")
    try:
        dxy = get_prices("DX-Y.NYB")
        dxy_ma = dxy.rolling(20).mean()
        dxy_d  = dxy_ma.reindex(prices.index, method="ffill")
        dxy_d_prev = dxy_ma.shift(5).reindex(prices.index, method="ffill")
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[dxy_d < dxy_d_prev] = 1  # DXY下落 → BTC有利
        return sig
    except Exception as e:
        print(f"  [C3 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_C4_crude(prices: pd.Series) -> pd.Series:
    """C4: 原油下落 × BTC"""
    print("  [C4] 原油 取得中...")
    try:
        crude  = get_prices("CL=F")
        cr_ma  = crude.rolling(20).mean()
        cr_d   = cr_ma.reindex(prices.index, method="ffill")
        cr_prev = cr_ma.shift(20).reindex(prices.index, method="ffill")
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[cr_d < cr_prev] = 1  # 原油下落時にBTC買い
        return sig
    except Exception as e:
        print(f"  [C4 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_C5_ism(prices: pd.Series) -> pd.Series:
    """C5: ISM PMI < 50 → BTC逆張り"""
    print("  [C5] FRED ISM代替 取得中...")
    try:
        # NAPM製造業 PMI 代替: MANEMP (製造業雇用者数変化)
        pmi = get_fred("NAPMPMI")
        pmi_d = pmi.reindex(prices.index, method="ffill")
        sig   = pd.Series(0, index=prices.index, dtype=float)
        sig[pmi_d < 50] = 1  # 景気悪化時に逆張り買い
        return sig
    except Exception as e:
        print(f"  [C5 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_C6_rate_vix(prices: pd.Series) -> pd.Series:
    """C6: 金利低下 + VIX < 20"""
    print("  [C6] FRED FF金利 + VIX 取得中...")
    try:
        ff  = get_fred("FEDFUNDS")
        vix = get_prices("^VIX")

        ff_d   = ff.reindex(prices.index, method="ffill")
        ff_prev = ff.shift(1).reindex(prices.index, method="ffill")
        vix_d  = vix.reindex(prices.index, method="ffill")

        sig = pd.Series(0, index=prices.index, dtype=float)
        rate_falling = ff_d < ff_prev
        low_vix      = vix_d < 20
        sig[rate_falling & low_vix] = 1
        return sig
    except Exception as e:
        print(f"  [C6 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


# ============================================================
# D. センチメント系
# ============================================================

def strategy_D1_google_trends(prices: pd.Series) -> pd.Series:
    """D1: Google Trends BTC検索数 — 急減時に買い (逆張り)"""
    print("  [D1] Google Trends 取得中...")
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360)
        pt.build_payload(["bitcoin"], timeframe="today 5-y")
        df = pt.interest_over_time()
        if df.empty:
            raise ValueError("empty trends")
        trend = df["bitcoin"].astype(float)
        trend.index = pd.to_datetime(trend.index)
        trend_d = trend.reindex(prices.index, method="ffill")
        ma = trend_d.rolling(8).mean()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[trend_d < ma * 0.7] = 1   # 検索急減 → 逆張り買い
        sig[trend_d > ma * 1.5] = -1  # 検索急増 → 過熱売り
        return sig
    except Exception as e:
        print(f"  [D1 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_D3_day_of_week(prices: pd.Series) -> pd.Series:
    """D3: 月曜/火曜効果 (月・火が平均リターン高い日に買い)"""
    # 曜日別平均リターンを計算してシグナル化
    rets = prices.pct_change()
    dow  = prices.index.dayofweek  # 0=月, 1=火
    avg  = {d: rets[dow == d].mean() for d in range(7)}
    best_days = sorted(avg, key=avg.get, reverse=True)[:2]
    sig = pd.Series(0, index=prices.index, dtype=float)
    for d in best_days:
        sig[prices.index.dayofweek == d] = 1
    return sig


def strategy_D4_month_start(prices: pd.Series) -> pd.Series:
    """D4: 月初効果 (月1-3日)"""
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[prices.index.day <= 3] = 1
    return sig


# ============================================================
# E. オルタナティブ系
# ============================================================

def strategy_E1_halloween(prices: pd.Series) -> pd.Series:
    """E1: ハロウィン効果 (10月-4月 保有)"""
    sig  = pd.Series(0, index=prices.index, dtype=float)
    month = prices.index.month
    sig[(month >= 10) | (month <= 4)] = 1
    return sig


def strategy_E2_month_end(prices: pd.Series) -> pd.Series:
    """E2: 月末リバランス (-3日〜月末)"""
    sig = pd.Series(0, index=prices.index, dtype=float)
    # 月末から3営業日前を特定
    for dt in prices.index:
        # その月の最終日を取得
        last_day = (dt.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days_to_end = (last_day - dt).days
        if 0 <= days_to_end <= 3:
            sig[dt] = 1
    return sig


def strategy_E3_earnings_season(prices: pd.Series) -> pd.Series:
    """E3: 決算シーズン (3,6,9,12月末前後10日)"""
    sig   = pd.Series(0, index=prices.index, dtype=float)
    month = prices.index.month
    day   = prices.index.day
    # 各四半期末月の後半
    in_season = (month.isin([3, 6, 9, 12]) & (day >= 20)) | \
                (month.isin([4, 7, 10, 1]) & (day <= 10))
    sig[in_season] = 1
    return sig


def strategy_E4_btc_dom_reversal(prices_eth: pd.Series, btc_dom: pd.Series) -> pd.Series:
    """E4: BTCドミナンス転換 (60%超→下落でETH買い)"""
    dom_d    = btc_dom.reindex(prices_eth.index, method="ffill")
    dom_prev = btc_dom.shift(5).reindex(prices_eth.index, method="ffill")
    sig = pd.Series(0, index=prices_eth.index, dtype=float)
    # 60%超から下落し始め
    was_high = dom_prev > 60
    falling  = dom_d < dom_prev
    sig[was_high & falling] = 1
    return sig


# ============================================================
# BTC Dominance 取得 (CoinGecko)
# ============================================================

def get_btc_dominance_series(prices_index: pd.DatetimeIndex) -> pd.Series:
    """BTC支配率の時系列 (簡易: 固定60%とする / API制限時フォールバック)"""
    # yfinanceにBTCDOMINANCEはないのでCoinGeckoから取得試み
    CG_KEY = os.environ.get("COINGECKO_API_KEY", "")
    try:
        headers = {"x-cg-demo-api-key": CG_KEY} if CG_KEY else {}
        r = requests.get(
            "https://api.coingecko.com/api/v3/global/market_cap_percentage",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            btc_pct = r.json().get("data", {}).get("btc", 50.0)
            # 単一値を全期間に展開
            return pd.Series(btc_pct, index=prices_index, dtype=float)
    except Exception:
        pass
    # フォールバック: 50%固定
    return pd.Series(50.0, index=prices_index, dtype=float)


# ============================================================
# M. モメンタム系
# ============================================================

def get_fear_greed_series(prices_index: pd.DatetimeIndex) -> pd.Series:
    """Fear & Greed Index の時系列取得 (Alternative.me API)"""
    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=2000&format=json",
            timeout=15
        )
        data = r.json().get("data", [])
        fg_dict = {}
        for d in data:
            ts = pd.Timestamp.fromtimestamp(int(d["timestamp"]))
            fg_dict[ts.normalize()] = float(d["value"])
        s = pd.Series(fg_dict, dtype=float).sort_index()
        return s.reindex(prices_index, method="ffill")
    except Exception as e:
        print(f"  [F&G skip] {e}")
        return pd.Series(np.nan, index=prices_index, dtype=float)


def backtest_custom(prices: pd.Series, entries: pd.Series,
                    hold_days: int = 10, stop: float = -0.08,
                    take_profit: float = 0.15, fee: float = 0.001) -> dict:
    """
    カスタムバックテストエンジン（モメンタム系向け）
    entries: エントリー日に1、それ以外は0のSeries
    OOS = 直近30%
    """
    prices  = prices.dropna()
    entries = entries.reindex(prices.index).fillna(0)

    if len(prices) < 10:
        empty = {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                 "win_rate": 0.0, "trades": 0, "pvalue": 1.0}
        return {"IS": empty, "OOS": empty}

    split = max(int(len(prices) * 0.7), 1)

    def _run(p: pd.Series, e: pd.Series) -> dict:
        capital = 1.0
        equity = []
        trades, wins = 0, 0
        pos = 0
        entry_price = 0.0
        hold = 0

        for i in range(len(p)):
            price = float(p.iloc[i])
            entry_sig = float(e.iloc[i])

            if pos != 0:
                ret = (price - entry_price) / entry_price
                hold += 1
                if ret <= stop or hold >= hold_days or ret >= take_profit:
                    capital *= (1 + ret - fee)
                    if ret > 0:
                        wins += 1
                    trades += 1
                    pos = 0

            if pos == 0 and entry_sig == 1:
                pos = 1
                entry_price = price * (1 + fee)
                hold = 0

            equity.append(capital)

        if pos != 0:
            ret = (float(p.iloc[-1]) - entry_price) / entry_price
            capital *= (1 + ret - fee)
            if ret > 0:
                wins += 1
            trades += 1

        equity = np.array(equity)
        if len(equity) == 0:
            return {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                    "win_rate": 0.0, "trades": 0, "pvalue": 1.0}

        rets = np.diff(equity) / (equity[:-1] + 1e-9)
        sharpe = float(np.mean(rets) / (np.std(rets) + 1e-9) * np.sqrt(252)) if len(rets) > 1 else 0.0
        peak = np.maximum.accumulate(equity)
        mdd = float(np.min(equity / (peak + 1e-9) - 1))
        win_r = wins / max(trades, 1) * 100
        total = float(capital - 1.0)

        pval = 1.0
        if len(rets) > 5:
            _, pval = stats.ttest_1samp(rets, 0)
            pval = float(pval)

        return {
            "sharpe": round(sharpe, 3),
            "total_return": round(total * 100, 1),
            "mdd": round(mdd * 100, 1),
            "win_rate": round(win_r, 1),
            "trades": trades,
            "pvalue": round(pval, 4),
        }

    return {
        "IS":  _run(prices.iloc[:split], entries.iloc[:split]),
        "OOS": _run(prices.iloc[split:], entries.iloc[split:]),
    }


def strategy_M1_volume_breakout(prices: pd.Series, vol: pd.Series,
                                  fg: pd.Series = None) -> pd.Series:
    """M1: 出来高2倍以上 × 20日高値更新 × F&G>40"""
    vol_ma = vol.rolling(20).mean()
    hi20   = prices.rolling(20).max().shift(1)

    cond_vol   = vol > vol_ma * 2
    cond_price = prices > hi20

    if fg is not None and fg.notna().any():
        cond_fg = fg > 40
    else:
        # F&Gデータなしの場合はスキップ（常にFalse）
        cond_fg = pd.Series(False, index=prices.index)

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[cond_vol & cond_price & cond_fg] = 1
    return sig


def strategy_M2_ath_breakout(prices: pd.Series) -> pd.Series:
    """M2: 過去250日最高値更新後3日以内エントリー"""
    ath250 = prices.rolling(250).max().shift(1)
    # ATH更新日を検出
    new_ath = prices > ath250
    # 更新後3日以内フラグ
    entry_window = new_ath.rolling(3).max().fillna(0).astype(bool)
    # ただし、ATH更新日当日は除外（翌日〜3日以内）
    entry = entry_window & ~new_ath
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[entry] = 1
    return sig


def strategy_M3_relative_momentum(prices_index: pd.DatetimeIndex) -> tuple:
    """
    M3: 相対トレンド週次
    BTC/ETH/SOL/ARM の20日リターン比較 → TOP1保有
    Returns: (prices, signals) のタプル
    """
    print("  [M3] 相対モメンタム用データ取得中...")
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "ARM"]
    try:
        all_data = {}
        for t in tickers:
            try:
                df = yf.download(t, period="5y", auto_adjust=True, progress=False)
                if len(df) > 50:
                    all_data[t] = df["Close"].dropna().squeeze()
            except Exception:
                pass

        if len(all_data) < 2:
            return None, None

        # 共通インデックスに整列
        combined = pd.DataFrame(all_data).dropna()
        if len(combined) < 30:
            return None, None

        # 20日リターン計算
        ret20 = combined.pct_change(20)

        # 週初め（月曜）のみシグナル更新
        signals_dict = {t: pd.Series(0, index=combined.index, dtype=float) for t in combined.columns}
        current_hold = None

        for i in range(20, len(combined)):
            dt = combined.index[i]
            if dt.dayofweek == 0:  # 月曜
                row = ret20.iloc[i]
                if row.notna().any():
                    best = row.idxmax()
                    current_hold = best

            if current_hold is not None:
                signals_dict[current_hold].iloc[i] = 1

        # BTCのシグナルを代表として返す（recordで使う形式に合わせる）
        btc_sig = signals_dict.get("BTC-USD", pd.Series(0, index=combined.index))
        # combined の全銘柄平均リターンで擬似ポートフォリオのシグナルを作成
        # 実際にはBTCのみで代表
        return combined["BTC-USD"], btc_sig

    except Exception as e:
        print(f"  [M3 skip] {e}")
        return None, None


def strategy_M4_sentiment_trend(prices: pd.Series, fg: pd.Series = None) -> pd.Series:
    """M4: F&G 7日前比+10以上 × 20日MA上昇中"""
    ma20 = prices.rolling(20).mean()
    above_ma = prices > ma20

    if fg is not None and fg.notna().any():
        fg_diff7 = fg - fg.shift(7)
        fg_rising = fg_diff7 >= 10
    else:
        print("  [M4] F&Gデータなし → シグナルゼロ")
        return pd.Series(0, index=prices.index, dtype=float)

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[fg_rising & above_ma] = 1
    return sig


def strategy_M5_absolute_trend(prices: pd.Series) -> pd.Series:
    """M5: 200日MA上 → 保有 / 200日MA下 → 現金"""
    ma200 = prices.rolling(200).mean()
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[prices > ma200] = 1
    return sig


# ============================================================
# MT. 新モメンタム系（Manus AIレポートより）
# ============================================================

def strategy_MT1_dual_momentum(prices_btc: pd.Series, prices_eth: pd.Series) -> tuple:
    """MT1: デュアルモメンタム（Antonacci 2014）
    絶対モメンタム × 相対モメンタム
    BTCの12ヶ月リターン > 0 かつ ETHより高い → BTC買い
    どちらも < 0 → 現金保有（毎月末リバランス）
    """
    combined = pd.DataFrame({"BTC": prices_btc, "ETH": prices_eth}).dropna()
    btc = combined["BTC"]
    eth = combined["ETH"]

    ret12_btc = btc.pct_change(252)
    ret12_eth = eth.pct_change(252)

    sig_btc = pd.Series(0, index=combined.index, dtype=float)
    current_pos = 0  # 0=cash, 1=BTC

    for i in range(252, len(combined)):
        dt = combined.index[i]
        is_month_end = (i == len(combined) - 1) or (combined.index[i + 1].month != dt.month)

        if is_month_end:
            r_btc = ret12_btc.iloc[i]
            r_eth = ret12_eth.iloc[i]
            if pd.isna(r_btc) or pd.isna(r_eth):
                current_pos = 0
            elif r_btc > 0 and r_btc >= r_eth:
                current_pos = 1  # BTC
            else:
                current_pos = 0  # ETH or cash → treat as cash for BTC signal

        sig_btc.iloc[i] = 1 if current_pos == 1 else 0

    return btc, sig_btc


def strategy_MT2_ts_momentum(prices: pd.Series) -> pd.Series:
    """MT2: タイムシリーズモメンタム（Moskowitz 2012）
    過去12ヶ月リターン > 0 → ロング（ボラティリティスケーリング付き）
    ショート不可なので否定は現金
    """
    ret12 = prices.pct_change(252)
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[ret12 > 0] = 1
    return sig


def strategy_MT3_risk_adjusted_momentum(prices: pd.Series) -> pd.Series:
    """MT3: リスク調整済みモメンタム（Barroso & Santa-Clara 2015）
    過去6ヶ月リターン / 過去6ヶ月ボラティリティ = モメンタムスコア
    スコア > 0.5 → エントリー
    """
    ret6 = prices.pct_change(126)
    vol6 = prices.pct_change().rolling(126).std() * np.sqrt(252)
    score = ret6 / (vol6 + 1e-9)

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[score > 0.5] = 1
    return sig


def strategy_MT4_momentum_crash_avoid(prices: pd.Series, fg: pd.Series = None) -> pd.Series:
    """MT4: モメンタムクラッシュ回避（Daniel & Moskowitz 2016）
    VIX > 30 または直近1ヶ月リターン < -20% または F&G < 20 → 現金
    通常時: 200日MAトレンドフォロー
    """
    print("  [MT4] VIX データ取得中...")
    try:
        vix = get_prices("^VIX")
        vix_d = vix.reindex(prices.index, method="ffill").fillna(25)
    except Exception as e:
        print(f"  [MT4 VIX skip] {e}")
        vix_d = pd.Series(25, index=prices.index, dtype=float)

    ret1m = prices.pct_change(21)

    crash_cond = (vix_d > 30) | (ret1m < -0.20)

    if fg is not None and fg.notna().any():
        crash_cond = crash_cond | (fg.fillna(50) < 20)

    ma200 = prices.rolling(200).mean()
    base_sig = (prices > ma200).astype(float)

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[~crash_cond] = base_sig[~crash_cond]
    return sig


def strategy_MT5_crypto_ts_momentum(prices_btc: pd.Series,
                                     prices_eth: pd.Series,
                                     prices_sol: pd.Series) -> tuple:
    """MT5: 暗号資産タイムシリーズモメンタム（Liu et al. 2021）
    週次で評価（日次ノイズ回避）
    BTC/ETH/SOL の3銘柄で多数決 → 2銘柄以上が過去4週プラスなら買い
    """
    combined = pd.DataFrame({"BTC": prices_btc, "ETH": prices_eth, "SOL": prices_sol}).dropna()
    weekly = combined.resample("W").last()
    ret4w = weekly.pct_change(4)

    votes = (ret4w > 0).sum(axis=1)
    any_crash = (ret4w < -0.10).any(axis=1)

    weekly_sig = pd.Series(0, index=weekly.index, dtype=float)
    weekly_sig[votes >= 2] = 1
    weekly_sig[any_crash] = 0

    sig = weekly_sig.reindex(prices_btc.index, method="ffill").fillna(0)
    return combined["BTC"], sig


def strategy_MT6_volume_weighted_momentum(prices: pd.Series, vol: pd.Series) -> pd.Series:
    """MT6: ボリューム加重モメンタム（Lee & Swaminathan 2000）
    出来高加重平均リターン > 0 × 出来高トレンド上昇 × 価格MA上
    """
    daily_ret = prices.pct_change()
    vol_weight = vol / (vol.rolling(10).sum() + 1e-9)
    vwap_ret = (daily_ret * vol_weight).rolling(10).sum()

    vol_ma10 = vol.rolling(10).mean()
    vol_ma20 = vol.rolling(20).mean()
    vol_trend_up = vol_ma10 > vol_ma20

    price_ma10 = prices.rolling(10).mean()
    price_above_ma = prices > price_ma10

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[(vwap_ret > 0) & vol_trend_up & price_above_ma] = 1
    return sig


def strategy_MT7_intraday_momentum(prices: pd.Series) -> pd.Series:
    """MT7: 短期イントラデイモメンタム（Gao et al. 2018 クリプト版）
    前日終値リターン > +1% → 翌日エントリー、5日保有、損切り-5%
    """
    daily_ret = prices.pct_change()
    prev_ret = daily_ret.shift(1)
    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[prev_ret > 0.01] = 1
    return sig


def strategy_MT8_factor_momentum(prices: pd.Series, vol: pd.Series,
                                   fg: pd.Series = None) -> pd.Series:
    """MT8: ファクターモメンタム（Arnott et al. 2021）
    価格モメンタム + 出来高モメンタム + センチメントモメンタムを0〜1正規化して合成
    3つ全てが 0.5 超の時のみエントリー
    """
    # ファクター1: 価格モメンタム（20日）
    ret20 = prices.pct_change(20)
    r20_mean = ret20.rolling(252).mean()
    r20_std  = ret20.rolling(252).std()
    f1 = ((ret20 - r20_mean) / (r20_std + 1e-9)).clip(-3, 3) / 6 + 0.5

    # ファクター2: 出来高モメンタム（20日）
    vol_ret20 = vol.pct_change(20)
    v20_mean  = vol_ret20.rolling(252).mean()
    v20_std   = vol_ret20.rolling(252).std()
    f2 = ((vol_ret20 - v20_mean) / (v20_std + 1e-9)).clip(-3, 3) / 6 + 0.5

    # ファクター3: センチメント
    if fg is not None and fg.notna().any():
        f3 = fg.fillna(50) / 100
    else:
        ma5  = prices.rolling(5).mean()
        ma20 = prices.rolling(20).mean()
        f3   = ((prices > ma5).astype(float) + (prices > ma20).astype(float)) / 2

    all_up   = (f1 > 0.5) & (f2 > 0.5) & (f3 > 0.5)
    composite = 0.4 * f1 + 0.3 * f2 + 0.3 * f3

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[all_up & (composite > 0.55)] = 1
    return sig


# ============================================================
# ME. 新モメンタム系（拡張3手法）
# ============================================================

def strategy_ME1_earnings_momentum(ticker: str) -> tuple:
    """ME1: アーニングスモメンタム（決算サプライズ）
    決算発表日翌営業日に前日比+3%以上上昇 → エントリー
    保有60日、損切-10%、利確+20%
    対象: NVDA, ARM, AAPL, MSFT
    """
    try:
        prices_df = yf.download(ticker, period="5y", auto_adjust=True, progress=False)
        if prices_df.empty:
            return None, None
        prices = prices_df["Close"].dropna().squeeze()

        stock = yf.Ticker(ticker)
        earnings_dates = []

        # 方法1: calendar
        try:
            cal = stock.calendar
            if cal is not None and isinstance(cal, dict):
                for key in ["Earnings Date", "earnings_date"]:
                    val = cal.get(key)
                    if val is not None:
                        if isinstance(val, (list, pd.DatetimeIndex)):
                            for d in val:
                                dt = pd.Timestamp(d).normalize()
                                if dt in prices.index:
                                    earnings_dates.append(dt)
                        else:
                            dt = pd.Timestamp(val).normalize()
                            if dt in prices.index:
                                earnings_dates.append(dt)
        except Exception:
            pass

        # 方法2: earnings_dates
        if not earnings_dates:
            try:
                ed = stock.earnings_dates
                if ed is not None and not ed.empty:
                    for d in ed.index:
                        # タイムゾーン除去して日次に変換
                        dt = pd.Timestamp(d).tz_localize(None).normalize()
                        if dt in prices.index:
                            earnings_dates.append(dt)
            except Exception:
                pass

        # フォールバック: 四半期末（3,6,9,12月の最終5日間）
        if not earnings_dates:
            seen = set()
            for dt in prices.index:
                if dt.month in [3, 6, 9, 12]:
                    next_month = dt.replace(day=28) + timedelta(days=4)
                    last_day = next_month.replace(day=1) - timedelta(days=1)
                    days_to_end = (last_day - dt).days
                    if 0 <= days_to_end <= 5:
                        key = (dt.year, dt.month)
                        if key not in seen:
                            earnings_dates.append(dt)
                            seen.add(key)

        # シグナル生成
        sig = pd.Series(0, index=prices.index, dtype=float)
        price_idx = list(prices.index)

        for earn_date in earnings_dates:
            try:
                pos = price_idx.index(earn_date)
                if pos + 1 < len(price_idx):
                    next_day = price_idx[pos + 1]
                    if prices[earn_date] > 0 and prices[next_day] / prices[earn_date] - 1 >= 0.03:
                        sig[next_day] = 1
            except (ValueError, KeyError):
                continue

        return prices, sig
    except Exception as e:
        print(f"  [ME1 {ticker} skip] {e}")
        return None, None


def strategy_ME2_bond_crypto_momentum(prices: pd.Series) -> pd.Series:
    """ME2: 債券×クリプト逆相関モメンタム
    FRED 10年債利回り（DGS10）前月比-0.1%pt以上低下 → ロング
    前月比+0.1%pt以上上昇 → ポジション解消
    保有30日
    """
    print("  [ME2] FRED DGS10 CSV取得中...")
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        from io import StringIO
        df_yield = pd.read_csv(StringIO(r.text), index_col=0, parse_dates=True)
        df_yield.columns = ["value"]
        df_yield = df_yield[df_yield["value"] != "."].copy()
        df_yield["value"] = df_yield["value"].astype(float)
        yields = df_yield["value"].dropna()

        # 月次リサンプル → 前月比変化
        monthly = yields.resample("ME").last()
        monthly_chg = monthly.diff()  # 単位: %pt

        # 日次に展開（forward fill）
        monthly_chg_d = monthly_chg.reindex(prices.index, method="ffill")

        # ポジション管理
        sig = pd.Series(0, index=prices.index, dtype=float)
        in_position = False
        for i in range(len(sig)):
            chg = monthly_chg_d.iloc[i]
            if pd.isna(chg):
                sig.iloc[i] = 1 if in_position else 0
                continue
            if not in_position and chg <= -0.1:
                in_position = True
            elif in_position and chg >= 0.1:
                in_position = False
            sig.iloc[i] = 1 if in_position else 0

        return sig
    except Exception as e:
        print(f"  [ME2 skip] {e}")
        return pd.Series(0, index=prices.index, dtype=float)


def strategy_ME3_ml_momentum(prices: pd.Series, vol: pd.Series) -> pd.Series:
    """ME3: ML強化モメンタム（線形回帰ベース）
    特徴量: 過去5/10/20日リターン、5日ボラ、出来高比率（当日/20日平均）
    目的変数: 翌5日リターン
    ローリング120日学習 → 予測値>2%でエントリー、<-1%で解消
    対象: BTC-USD, ETH-USD
    """
    try:
        from sklearn.linear_model import LinearRegression
        _lr_available = True
    except ImportError:
        print("  [ME3] scikit-learn なし → シグナルゼロ")
        return pd.Series(0, index=prices.index, dtype=float)

    daily_ret = prices.pct_change()
    vol_ma20 = vol.rolling(20).mean()
    vol_ratio = vol / (vol_ma20 + 1e-9)

    ret5  = prices.pct_change(5)
    ret10 = prices.pct_change(10)
    ret20 = prices.pct_change(20)
    vol5  = daily_ret.rolling(5).std()

    # 翌5日リターン（目的変数）
    target = prices.pct_change(5).shift(-5)

    feature_df = pd.DataFrame({
        "ret5":      ret5,
        "ret10":     ret10,
        "ret20":     ret20,
        "vol5":      vol5,
        "vol_ratio": vol_ratio,
    })

    combined = pd.concat([feature_df, target.rename("target")], axis=1).dropna()
    if len(combined) < 130:
        return pd.Series(0, index=prices.index, dtype=float)

    LOOKBACK = 120
    model = LinearRegression()
    sig = pd.Series(0, index=prices.index, dtype=float)
    prev_sig = 0

    for i in range(LOOKBACK, len(combined)):
        train = combined.iloc[i - LOOKBACK:i]
        train_X = train[["ret5", "ret10", "ret20", "vol5", "vol_ratio"]].values
        train_y = train["target"].values

        if np.isnan(train_X).any() or np.isnan(train_y).any():
            continue

        try:
            model.fit(train_X, train_y)
            pred_X = combined.iloc[i:i+1][["ret5", "ret10", "ret20", "vol5", "vol_ratio"]].values
            if np.isnan(pred_X).any():
                continue
            pred = float(model.predict(pred_X)[0])

            dt = combined.index[i]
            if dt in sig.index:
                if pred > 0.02:
                    prev_sig = 1
                elif pred < -0.01:
                    prev_sig = 0
                sig[dt] = prev_sig
        except Exception:
            continue

    return sig


# ============================================================
# AC. 学術的資産配分戦略
# ============================================================

def backtest_portfolio_is_oos(equity: np.ndarray) -> dict:
    """ポートフォリオエクイティカーブからIS/OOSメトリクスを計算"""
    if len(equity) < 10:
        empty = {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                 "win_rate": 0.0, "trades": 0, "pvalue": 1.0}
        return {"IS": empty, "OOS": empty}

    split = max(int(len(equity) * 0.7), 1)

    def _stats(eq: np.ndarray) -> dict:
        if len(eq) < 3:
            return {"sharpe": 0.0, "total_return": 0.0, "mdd": 0.0,
                    "win_rate": 0.0, "trades": 0, "pvalue": 1.0}
        rets = np.diff(eq) / (eq[:-1] + 1e-9)
        sharpe = float(np.mean(rets) / (np.std(rets) + 1e-9) * np.sqrt(252))
        peak = np.maximum.accumulate(eq)
        mdd = float(np.min(eq / (peak + 1e-9) - 1))
        total = float(eq[-1] / eq[0] - 1.0)
        win_r = float((rets > 0).mean() * 100)
        pval = 1.0
        if len(rets) > 5:
            _, pval = stats.ttest_1samp(rets, 0)
            pval = float(pval)
        return {
            "sharpe": round(sharpe, 3),
            "total_return": round(total * 100, 1),
            "mdd": round(mdd * 100, 1),
            "win_rate": round(win_r, 1),
            "trades": len(rets),
            "pvalue": round(pval, 4),
        }

    return {"IS": _stats(equity[:split]), "OOS": _stats(equity[split:])}


def strategy_AC1_rebalance() -> np.ndarray:
    """AC1: 定期リバランス (Perold & Sharpe 1988)
    BTC/ETH/SOL/ARM を25%ずつ毎月末リバランス
    """
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "ARM"]
    fee = 0.001
    try:
        all_data = {}
        for t in tickers:
            try:
                df = yf.download(t, period="3y", auto_adjust=True, progress=False)
                if len(df) > 50:
                    all_data[t] = df["Close"].dropna().squeeze()
            except Exception:
                pass

        if len(all_data) < 2:
            return None

        combined = pd.DataFrame(all_data).dropna()
        if len(combined) < 60:
            return None

        returns = combined.pct_change().fillna(0)
        n = len(combined.columns)
        eq_w = 1.0 / n
        weights = {t: eq_w for t in combined.columns}
        equity = [1.0]

        for i in range(1, len(combined)):
            port_ret = sum(weights[t] * float(returns.iloc[i][t]) for t in combined.columns)
            new_val = equity[-1] * (1 + port_ret)

            # 月初（前日と月が異なる）にリバランス
            if combined.index[i].month != combined.index[i - 1].month:
                total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in combined.columns)
                if total_w > 0:
                    actual_w = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                                for t in combined.columns}
                else:
                    actual_w = {t: eq_w for t in combined.columns}
                turnover = sum(abs(actual_w[t] - eq_w) for t in combined.columns) / 2
                new_val *= (1 - fee * turnover * 2)
                weights = {t: eq_w for t in combined.columns}
            else:
                total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in combined.columns)
                if total_w > 0:
                    weights = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                               for t in combined.columns}

            equity.append(new_val)

        return np.array(equity)
    except Exception as e:
        print(f"  [AC1 error] {e}")
        return None


def strategy_AC2_risk_parity() -> np.ndarray:
    """AC2: リスクパリティ (Qian 2005)
    各銘柄のボラの逆数でウェイト決定、毎月更新
    対象: BTC/ETH/SOL/AGG
    """
    tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "AGG"]
    fee = 0.001
    LOOKBACK = 20
    try:
        all_data = {}
        for t in tickers:
            try:
                df = yf.download(t, period="3y", auto_adjust=True, progress=False)
                if len(df) > 50:
                    all_data[t] = df["Close"].dropna().squeeze()
            except Exception:
                pass

        if len(all_data) < 2:
            return None

        combined = pd.DataFrame(all_data).dropna()
        if len(combined) < LOOKBACK + 10:
            return None

        returns = combined.pct_change().fillna(0)
        assets = list(combined.columns)

        weights = {t: 1.0 / len(assets) for t in assets}
        equity = [1.0]

        for i in range(1, len(combined)):
            port_ret = sum(weights[t] * float(returns.iloc[i][t]) for t in assets)
            new_val = equity[-1] * (1 + port_ret)

            # 月初にリスクパリティウェイト更新
            if combined.index[i].month != combined.index[i - 1].month and i >= LOOKBACK:
                hist_rets = returns.iloc[max(0, i - LOOKBACK):i]
                vols = {t: float(hist_rets[t].std()) + 1e-9 for t in assets}
                inv_vols = {t: 1.0 / vols[t] for t in assets}
                total_inv = sum(inv_vols.values())
                new_weights = {t: inv_vols[t] / total_inv for t in assets}

                total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in assets)
                if total_w > 0:
                    old_actual = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                                  for t in assets}
                else:
                    old_actual = {t: 1.0 / len(assets) for t in assets}

                turnover = sum(abs(new_weights[t] - old_actual[t]) for t in assets) / 2
                new_val *= (1 - fee * turnover * 2)
                weights = new_weights
            else:
                total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in assets)
                if total_w > 0:
                    weights = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                               for t in assets}

            equity.append(new_val)

        return np.array(equity)
    except Exception as e:
        print(f"  [AC2 error] {e}")
        return None


def strategy_AC3_dca(ticker: str = "BTC-USD") -> tuple:
    """AC3: DCA vs 一括投資 (毎月定額積立 vs 全額一括)
    Returns: (dca_equity, lump_equity) numpy arrays
    """
    fee = 0.001
    try:
        df = yf.download(ticker, period="3y", auto_adjust=True, progress=False)
        if df.empty or len(df) < 60:
            return None, None
        prices = df["Close"].dropna().squeeze()

        months = sorted(set(zip(prices.index.year, prices.index.month)))
        n_months = max(len(months), 1)
        monthly_invest = 1.0 / n_months

        dca_cash = 1.0
        dca_holdings = 0.0
        dca_equity = []
        month_invested = set()

        for i in range(len(prices)):
            price = float(prices.iloc[i])
            dt = prices.index[i]
            ym = (dt.year, dt.month)

            if ym not in month_invested and dca_cash >= monthly_invest * 0.99:
                invest_amount = min(monthly_invest, dca_cash)
                shares = invest_amount * (1 - fee) / price
                dca_holdings += shares
                dca_cash -= invest_amount
                month_invested.add(ym)

            portfolio_value = dca_cash + dca_holdings * price
            dca_equity.append(portfolio_value)

        initial_price = float(prices.iloc[0])
        lump_shares = (1.0 * (1 - fee)) / initial_price
        lump_equity = [lump_shares * float(p) for p in prices]

        return np.array(dca_equity), np.array(lump_equity)
    except Exception as e:
        print(f"  [AC3 error] {e}")
        return None, None


def strategy_AC4_low_vol(prices_btc: pd.Series, prices_eth: pd.Series,
                          prices_sol: pd.Series = None,
                          prices_arm: pd.Series = None) -> tuple:
    """AC4: 低ボラティリティ戦略 (Frazzini & Pedersen 2014)
    毎週、過去20日ボラが最も低い2銘柄を等配分保有
    """
    fee = 0.001
    LOOKBACK = 20
    try:
        assets = {"BTC": prices_btc, "ETH": prices_eth}
        if prices_sol is not None and len(prices_sol) > 50:
            assets["SOL"] = prices_sol
        if prices_arm is not None and len(prices_arm) > 50:
            assets["ARM"] = prices_arm

        combined = pd.DataFrame(assets).dropna()
        if len(combined) < LOOKBACK + 10:
            return None, None

        returns = combined.pct_change().fillna(0)
        asset_names = list(combined.columns)
        n_select = min(2, len(asset_names))

        weights = {t: 1.0 / len(asset_names) for t in asset_names}
        equity = [1.0]

        for i in range(1, len(combined)):
            dt = combined.index[i]

            # 毎週月曜日にリバランス
            if dt.dayofweek == 0 and i >= LOOKBACK:
                hist_rets = returns.iloc[max(0, i - LOOKBACK):i]
                vols = {t: float(hist_rets[t].std()) for t in asset_names}
                sorted_assets = sorted(vols.keys(), key=lambda x: vols[x])
                selected = sorted_assets[:n_select]

                new_weights = {t: 0.0 for t in asset_names}
                for t in selected:
                    new_weights[t] = 1.0 / n_select

                turnover = sum(abs(new_weights[t] - weights[t]) for t in asset_names) / 2
                equity[-1] *= (1 - fee * turnover * 2)
                weights = new_weights

            port_ret = sum(weights[t] * float(returns.iloc[i][t]) for t in asset_names)
            new_val = equity[-1] * (1 + port_ret)

            total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in asset_names)
            if total_w > 0:
                weights = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                           for t in asset_names}

            equity.append(new_val)

        return combined["BTC"], np.array(equity)
    except Exception as e:
        print(f"  [AC4 error] {e}")
        return None, None


def strategy_AC5_carry(prices: pd.Series) -> pd.Series:
    """AC5: クリプトキャリー (Lustig & Verdelhan 2007)
    ファンディングレートの代理変数として価格モメンタムを使用
    30日リターン > 40%（過熱=高FR代理）→ スキップ
    30日リターン < -15%（売り圧力=低FR代理）→ ロング
    通常時: 200日MA上であれば保有
    """
    ret30 = prices.pct_change(30)
    ma200 = prices.rolling(200).mean()

    overheated = ret30 > 0.40
    sell_pressure = ret30 < -0.15
    trend_ok = prices > ma200

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[trend_ok & ~overheated] = 1
    sig[sell_pressure] = 1
    sig[overheated] = 0
    return sig


def strategy_AC6_smart_beta(prices_btc: pd.Series, prices_eth: pd.Series,
                              prices_sol: pd.Series = None,
                              prices_arm: pd.Series = None) -> tuple:
    """AC6: スマートベータ複合 (Arnott et al. 2005)
    バリュー + モメンタム + クオリティ の3ファクター合成
    週次で上位2銘柄を選択
    """
    fee = 0.001
    WINDOW = 20
    try:
        assets = {"BTC": prices_btc, "ETH": prices_eth}
        if prices_sol is not None and len(prices_sol) > 50:
            assets["SOL"] = prices_sol
        if prices_arm is not None and len(prices_arm) > 50:
            assets["ARM"] = prices_arm

        combined = pd.DataFrame(assets).dropna()
        if len(combined) < WINDOW + 10:
            return None, None

        returns = combined.pct_change().fillna(0)
        asset_names = list(combined.columns)
        n_select = min(2, len(asset_names))

        weights = {t: 1.0 / len(asset_names) for t in asset_names}
        equity = [1.0]

        for i in range(1, len(combined)):
            dt = combined.index[i]

            # 週次（月曜）にスコア更新・リバランス
            if dt.dayofweek == 0 and i >= WINDOW:
                hist_rets = returns.iloc[max(0, i - WINDOW):i]
                hist_252 = combined.iloc[max(0, i - 252):i]
                scores = {}
                for t in asset_names:
                    # モメンタムスコア: 過去20日リターン
                    mom = float(combined.iloc[i][t] / combined.iloc[i - WINDOW][t] - 1)
                    # クオリティスコア: ボラの逆数（正規化）
                    vol = float(hist_rets[t].std()) + 1e-9
                    qual = min(1.0 / (vol * 100), 1.0)
                    # バリュースコア: Zスコアの逆数（低Z = 割安）
                    h_mean = float(hist_252[t].mean()) if len(hist_252) > 5 else float(combined.iloc[i][t])
                    h_std = float(hist_252[t].std()) + 1e-9 if len(hist_252) > 5 else 1.0
                    z_score = (float(combined.iloc[i][t]) - h_mean) / h_std
                    val_n = float(np.clip(-z_score / 3 * 0.5 + 0.5, 0, 1))
                    mom_n = float(np.clip(mom / 0.5 * 0.5 + 0.5, 0, 1))
                    scores[t] = (mom_n + qual + val_n) / 3

                sorted_assets = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
                selected = sorted_assets[:n_select]

                new_weights = {t: 0.0 for t in asset_names}
                for t in selected:
                    new_weights[t] = 1.0 / n_select

                turnover = sum(abs(new_weights[t] - weights[t]) for t in asset_names) / 2
                equity[-1] *= (1 - fee * turnover * 2)
                weights = new_weights

            port_ret = sum(weights[t] * float(returns.iloc[i][t]) for t in asset_names)
            new_val = equity[-1] * (1 + port_ret)

            total_w = sum(weights[t] * (1 + float(returns.iloc[i][t])) for t in asset_names)
            if total_w > 0:
                weights = {t: weights[t] * (1 + float(returns.iloc[i][t])) / total_w
                           for t in asset_names}

            equity.append(new_val)

        return combined["BTC"], np.array(equity)
    except Exception as e:
        print(f"  [AC6 error] {e}")
        return None, None


def strategy_AC7_event_driven(prices: pd.Series) -> pd.Series:
    """AC7: マクロイベント逆張り (Ball & Brown 1968 応用)
    BTC前日比 -5%以上の急落（FOMC等のマクロショック代理）→ 翌日逆張りエントリー
    保有期間5日、損切-5%（backtest_customで管理）
    """
    daily_ret = prices.pct_change()
    big_drop = daily_ret.shift(1) <= -0.05

    sig = pd.Series(0, index=prices.index, dtype=float)
    sig[big_drop] = 1
    return sig


# ============================================================
# スコアリング関数
# ============================================================

def calc_total_score(r: dict) -> int:
    """100点満点の総合スコアを計算"""
    score = 0

    # p値スコア (30点)
    p = r.get('pvalue', 1.0)
    if p < 0.01:   score += 30
    elif p < 0.05: score += 20
    elif p < 0.10: score += 10

    # シャープ比スコア (25点)
    sh = r.get('sharpe', 0)
    if sh > 2.0:   score += 25
    elif sh > 1.0: score += 15
    elif sh > 0.5: score += 5

    # EVスコア (20点) — total_returnで判定
    tr = r.get('total_return', 0)
    if tr > 10:   score += 20
    elif tr > 5:  score += 12
    elif tr > 2:  score += 5

    # DDスコア (15点)
    dd = abs(r.get('mdd', 100))
    if dd < 10:   score += 15
    elif dd < 20: score += 8
    elif dd < 30: score += 3

    # サンプル数スコア (10点)
    n = r.get('trades', 0)
    if n > 50:   score += 10
    elif n > 30: score += 6
    elif n > 10: score += 2

    return score


def get_signal_color(score: int) -> str:
    if score >= 80: return "🟢"
    elif score >= 50: return "🟡"
    else: return "🔴"


def get_signal_label(score: int) -> str:
    if score >= 80: return "本番候補"
    elif score >= 50: return "検証継続"
    else: return "廃棄"


# ============================================================
# メイン実行
# ============================================================

def run_all():
    print("=" * 60)
    print("投資手法 完全検証エンジン v1.0")
    print("=" * 60)

    # 価格データ取得
    print("\n[データ取得] BTC/ETH...")
    btc_full = yf.download("BTC-USD", period="5y", auto_adjust=True, progress=False)
    eth_full = yf.download("ETH-USD", period="5y", auto_adjust=True, progress=False)

    btc_p  = btc_full["Close"].dropna().squeeze()
    eth_p  = eth_full["Close"].dropna().squeeze()
    btc_vol = btc_full["Volume"].dropna().squeeze()
    eth_vol = eth_full["Volume"].dropna().squeeze()

    print(f"  BTC: {len(btc_p)} 日分  ETH: {len(eth_p)} 日分")

    btc_dom = get_btc_dominance_series(btc_p.index)

    results = []

    def record(name, code, ticker_name, prices, signals):
        res = backtest(prices, signals)
        r   = {
            "code": code,
            "name": name,
            "ticker": ticker_name,
            **res["OOS"],
            "IS_sharpe": res["IS"]["sharpe"],
        }
        results.append(r)
        oos = res["OOS"]
        print(f"  [{code}] {ticker_name:3s} | "
              f"Sharpe={oos['sharpe']:+.2f} | "
              f"Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | "
              f"Win={oos['win_rate']:.0f}% | "
              f"p={oos['pvalue']:.3f} | "
              f"T={oos['trades']}")

    # ---- A. テクニカル ----
    print("\n[A] テクニカル系")

    record("MACD クロスオーバー", "A1", "BTC", btc_p, strategy_A1_macd(btc_p))
    record("MACD クロスオーバー", "A1", "ETH", eth_p, strategy_A1_macd(eth_p))

    record("出来高急増+価格ブレイク", "A2", "BTC", btc_p, strategy_A2_vol_breakout(btc_p, btc_vol))
    record("出来高急増+価格ブレイク", "A2", "ETH", eth_p, strategy_A2_vol_breakout(eth_p, eth_vol))

    record("ゴールデンクロス", "A3", "BTC", btc_p, strategy_A3_golden_cross(btc_p))
    record("ゴールデンクロス", "A3", "ETH", eth_p, strategy_A3_golden_cross(eth_p))

    record("BBスクイーズ", "A4", "BTC", btc_p, strategy_A4_bb_squeeze(btc_p))
    record("BBスクイーズ", "A4", "ETH", eth_p, strategy_A4_bb_squeeze(eth_p))

    record("週足Zスコア逆張り", "A5", "BTC", btc_p, strategy_A5_weekly_z(btc_p))
    record("週足Zスコア逆張り", "A5", "ETH", eth_p, strategy_A5_weekly_z(eth_p))

    record("月足RSI逆張り", "A6", "BTC", btc_p, strategy_A6_monthly_rsi(btc_p))
    record("月足RSI逆張り", "A6", "ETH", eth_p, strategy_A6_monthly_rsi(eth_p))

    # ---- B. ファンダメンタル ----
    print("\n[B] ファンダメンタル系")

    # B1: NVT (出来高で代替)
    record("NVT逆張り", "B1", "BTC", btc_p, strategy_B1_nvt(btc_p, btc_vol))

    record("半減期後サイクル", "B2", "BTC", btc_p, strategy_B2_halving(btc_p))

    record("BTC支配率→ETH", "B3", "ETH", eth_p, strategy_B3_btc_dom(eth_p, btc_dom))

    # ---- C. マクロ ----
    print("\n[C] マクロ系")

    record("逆イールド解消", "C1", "BTC", btc_p, strategy_C1_yield_curve(btc_p))
    record("逆イールド解消", "C1", "ETH", eth_p, strategy_C1_yield_curve(eth_p))

    record("M2増加率>5%", "C2", "BTC", btc_p, strategy_C2_m2(btc_p))

    record("DXY下落", "C3", "BTC", btc_p, strategy_C3_dxy(btc_p))

    record("原油下落×BTC", "C4", "BTC", btc_p, strategy_C4_crude(btc_p))

    record("ISM PMI<50逆張り", "C5", "BTC", btc_p, strategy_C5_ism(btc_p))

    record("金利低下+VIX<20", "C6", "BTC", btc_p, strategy_C6_rate_vix(btc_p))
    record("金利低下+VIX<20", "C6", "ETH", eth_p, strategy_C6_rate_vix(eth_p))

    # ---- D. センチメント ----
    print("\n[D] センチメント系")

    record("Googleトレンド逆張り", "D1", "BTC", btc_p, strategy_D1_google_trends(btc_p))

    record("曜日効果(月・火)", "D3", "BTC", btc_p, strategy_D3_day_of_week(btc_p))
    record("曜日効果(月・火)", "D3", "ETH", eth_p, strategy_D3_day_of_week(eth_p))

    record("月初効果(1-3日)", "D4", "BTC", btc_p, strategy_D4_month_start(btc_p))
    record("月初効果(1-3日)", "D4", "ETH", eth_p, strategy_D4_month_start(eth_p))

    # ---- E. オルタナティブ ----
    print("\n[E] オルタナティブ系")

    record("ハロウィン効果", "E1", "BTC", btc_p, strategy_E1_halloween(btc_p))
    record("ハロウィン効果", "E1", "ETH", eth_p, strategy_E1_halloween(eth_p))

    record("月末リバランス", "E2", "BTC", btc_p, strategy_E2_month_end(btc_p))
    record("月末リバランス", "E2", "ETH", eth_p, strategy_E2_month_end(eth_p))

    record("決算シーズン", "E3", "BTC", btc_p, strategy_E3_earnings_season(btc_p))
    record("決算シーズン", "E3", "ETH", eth_p, strategy_E3_earnings_season(eth_p))

    record("BTCドミナンス転換→ETH", "E4", "ETH", eth_p, strategy_E4_btc_dom_reversal(eth_p, btc_dom))

    # ---- M. モメンタム系 ----
    print("\n[M] モメンタム系")

    # Fear & Greed 取得
    print("  [M] Fear & Greed データ取得中...")
    fg_series = get_fear_greed_series(btc_p.index)

    # M1: 出来高×ブレイクアウト
    try:
        m1_sig = strategy_M1_volume_breakout(btc_p, btc_vol, fg_series)
        res_m1 = backtest_custom(btc_p, m1_sig, hold_days=10, stop=-0.08, take_profit=0.15)
        r_m1 = {"code": "M1", "name": "出来高×ブレイクアウト", "ticker": "BTC",
                **res_m1["OOS"], "IS_sharpe": res_m1["IS"]["sharpe"]}
        results.append(r_m1)
        oos = res_m1["OOS"]
        print(f"  [M1] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [M1 error] {e}")
        results.append({"code": "M1", "name": "出来高×ブレイクアウト", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # M2: ATH突破トレンド
    try:
        m2_sig = strategy_M2_ath_breakout(btc_p)
        res_m2 = backtest_custom(btc_p, m2_sig, hold_days=20, stop=-0.10, take_profit=0.20)
        r_m2 = {"code": "M2", "name": "ATH突破トレンド", "ticker": "BTC",
                **res_m2["OOS"], "IS_sharpe": res_m2["IS"]["sharpe"]}
        results.append(r_m2)
        oos = res_m2["OOS"]
        print(f"  [M2] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [M2 error] {e}")
        results.append({"code": "M2", "name": "ATH突破トレンド", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # M3: 相対トレンド週次
    try:
        m3_prices, m3_sig = strategy_M3_relative_momentum(btc_p.index)
        if m3_prices is not None and m3_sig is not None:
            res_m3 = backtest_custom(m3_prices, m3_sig, hold_days=7, stop=-0.10, take_profit=0.25)
            r_m3 = {"code": "M3", "name": "相対トレンド週次", "ticker": "BTC",
                    **res_m3["OOS"], "IS_sharpe": res_m3["IS"]["sharpe"]}
        else:
            res_m3 = {"OOS": {"sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0, "win_rate": 0, "trades": 0},
                      "IS": {"sharpe": 0}}
            r_m3 = {"code": "M3", "name": "相対トレンド週次", "ticker": "BTC",
                    **res_m3["OOS"], "IS_sharpe": 0}
        results.append(r_m3)
        oos = res_m3["OOS"]
        print(f"  [M3] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [M3 error] {e}")
        results.append({"code": "M3", "name": "相対トレンド週次", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # M4: センチメントトレンド
    try:
        m4_sig = strategy_M4_sentiment_trend(btc_p, fg_series)
        res_m4 = backtest_custom(btc_p, m4_sig, hold_days=15, stop=-0.08, take_profit=0.20)
        r_m4 = {"code": "M4", "name": "センチメントトレンド", "ticker": "BTC",
                **res_m4["OOS"], "IS_sharpe": res_m4["IS"]["sharpe"]}
        results.append(r_m4)
        oos = res_m4["OOS"]
        print(f"  [M4] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [M4 error] {e}")
        results.append({"code": "M4", "name": "センチメントトレンド", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # M5: 絶対トレンドフィルター
    try:
        m5_sig = strategy_M5_absolute_trend(btc_p)
        res_m5 = backtest(btc_p, m5_sig, lev=1.0, stop=-0.15, hold_days=365)
        r_m5 = {"code": "M5", "name": "絶対トレンドフィルター", "ticker": "BTC",
                **res_m5["OOS"], "IS_sharpe": res_m5["IS"]["sharpe"]}
        results.append(r_m5)
        oos = res_m5["OOS"]
        print(f"  [M5] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [M5 error] {e}")
        results.append({"code": "M5", "name": "絶対トレンドフィルター", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ---- MT. 新モメンタム系（Manus AIレポート 8手法） ----
    print("\n[MT] 新モメンタム系（Manus AIレポート）")

    # SOL データ取得
    print("  [MT] SOL-USD データ取得中...")
    try:
        sol_full = yf.download("SOL-USD", period="5y", auto_adjust=True, progress=False)
        sol_p = sol_full["Close"].dropna().squeeze()
    except Exception as e:
        print(f"  [MT] SOL スキップ: {e}")
        sol_p = btc_p.copy() * 0  # fallback

    # MT1: デュアルモメンタム
    try:
        mt1_prices, mt1_sig = strategy_MT1_dual_momentum(btc_p, eth_p)
        res_mt1 = backtest_custom(mt1_prices, mt1_sig, hold_days=30, stop=-0.15, take_profit=0.40, fee=0.001)
        r_mt1 = {"code": "MT1", "name": "デュアルモメンタム(Antonacci)", "ticker": "BTC",
                 **res_mt1["OOS"], "IS_sharpe": res_mt1["IS"]["sharpe"]}
        results.append(r_mt1)
        oos = res_mt1["OOS"]
        print(f"  [MT1] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT1 error] {e}")
        results.append({"code": "MT1", "name": "デュアルモメンタム(Antonacci)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT2: タイムシリーズモメンタム
    try:
        mt2_sig_btc = strategy_MT2_ts_momentum(btc_p)
        mt2_sig_eth = strategy_MT2_ts_momentum(eth_p)
        res_mt2_btc = backtest_custom(btc_p, mt2_sig_btc, hold_days=30, stop=-0.15, take_profit=0.50, fee=0.001)
        res_mt2_eth = backtest_custom(eth_p, mt2_sig_eth, hold_days=30, stop=-0.15, take_profit=0.50, fee=0.001)
        for ticker, prices_x, res_mt2 in [("BTC", btc_p, res_mt2_btc), ("ETH", eth_p, res_mt2_eth)]:
            r = {"code": "MT2", "name": "タイムシリーズモメンタム(Moskowitz)", "ticker": ticker,
                 **res_mt2["OOS"], "IS_sharpe": res_mt2["IS"]["sharpe"]}
            results.append(r)
            oos = res_mt2["OOS"]
            print(f"  [MT2] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT2 error] {e}")
        results.append({"code": "MT2", "name": "タイムシリーズモメンタム(Moskowitz)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT3: リスク調整済みモメンタム
    try:
        mt3_sig_btc = strategy_MT3_risk_adjusted_momentum(btc_p)
        mt3_sig_eth = strategy_MT3_risk_adjusted_momentum(eth_p)
        res_mt3_btc = backtest_custom(btc_p, mt3_sig_btc, hold_days=21, stop=-0.10, take_profit=0.30, fee=0.001)
        res_mt3_eth = backtest_custom(eth_p, mt3_sig_eth, hold_days=21, stop=-0.10, take_profit=0.30, fee=0.001)
        for ticker, res_mt3 in [("BTC", res_mt3_btc), ("ETH", res_mt3_eth)]:
            r = {"code": "MT3", "name": "リスク調整済みモメンタム(BSC)", "ticker": ticker,
                 **res_mt3["OOS"], "IS_sharpe": res_mt3["IS"]["sharpe"]}
            results.append(r)
            oos = res_mt3["OOS"]
            print(f"  [MT3] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT3 error] {e}")
        results.append({"code": "MT3", "name": "リスク調整済みモメンタム(BSC)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT4: モメンタムクラッシュ回避
    try:
        mt4_sig = strategy_MT4_momentum_crash_avoid(btc_p, fg_series)
        res_mt4 = backtest_custom(btc_p, mt4_sig, hold_days=30, stop=-0.15, take_profit=0.40, fee=0.001)
        r_mt4 = {"code": "MT4", "name": "クラッシュ回避モメンタム(DM2016)", "ticker": "BTC",
                 **res_mt4["OOS"], "IS_sharpe": res_mt4["IS"]["sharpe"]}
        results.append(r_mt4)
        oos = res_mt4["OOS"]
        print(f"  [MT4] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT4 error] {e}")
        results.append({"code": "MT4", "name": "クラッシュ回避モメンタム(DM2016)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT5: 暗号資産タイムシリーズモメンタム
    try:
        mt5_prices, mt5_sig = strategy_MT5_crypto_ts_momentum(btc_p, eth_p, sol_p)
        if mt5_prices is not None and mt5_sig is not None:
            res_mt5 = backtest_custom(mt5_prices, mt5_sig, hold_days=7, stop=-0.10, take_profit=0.20, fee=0.001)
            r_mt5 = {"code": "MT5", "name": "暗号資産TSモメンタム(Liu2021)", "ticker": "BTC",
                     **res_mt5["OOS"], "IS_sharpe": res_mt5["IS"]["sharpe"]}
        else:
            r_mt5 = {"code": "MT5", "name": "暗号資産TSモメンタム(Liu2021)", "ticker": "BTC",
                     "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                     "win_rate": 0, "trades": 0, "IS_sharpe": 0}
        results.append(r_mt5)
        oos = r_mt5
        print(f"  [MT5] BTC | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
              f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT5 error] {e}")
        results.append({"code": "MT5", "name": "暗号資産TSモメンタム(Liu2021)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT6: ボリューム加重モメンタム
    try:
        mt6_sig_btc = strategy_MT6_volume_weighted_momentum(btc_p, btc_vol)
        mt6_sig_eth = strategy_MT6_volume_weighted_momentum(eth_p, eth_vol)
        res_mt6_btc = backtest_custom(btc_p, mt6_sig_btc, hold_days=10, stop=-0.07, take_profit=0.15, fee=0.001)
        res_mt6_eth = backtest_custom(eth_p, mt6_sig_eth, hold_days=10, stop=-0.07, take_profit=0.15, fee=0.001)
        for ticker, res_mt6 in [("BTC", res_mt6_btc), ("ETH", res_mt6_eth)]:
            r = {"code": "MT6", "name": "ボリューム加重モメンタム(LS2000)", "ticker": ticker,
                 **res_mt6["OOS"], "IS_sharpe": res_mt6["IS"]["sharpe"]}
            results.append(r)
            oos = res_mt6["OOS"]
            print(f"  [MT6] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT6 error] {e}")
        results.append({"code": "MT6", "name": "ボリューム加重モメンタム(LS2000)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT7: 短期イントラデイモメンタム
    try:
        mt7_sig_btc = strategy_MT7_intraday_momentum(btc_p)
        mt7_sig_eth = strategy_MT7_intraday_momentum(eth_p)
        res_mt7_btc = backtest_custom(btc_p, mt7_sig_btc, hold_days=5, stop=-0.05, take_profit=0.08, fee=0.001)
        res_mt7_eth = backtest_custom(eth_p, mt7_sig_eth, hold_days=5, stop=-0.05, take_profit=0.08, fee=0.001)
        for ticker, res_mt7 in [("BTC", res_mt7_btc), ("ETH", res_mt7_eth)]:
            r = {"code": "MT7", "name": "短期イントラデイモメンタム(Gao2018)", "ticker": ticker,
                 **res_mt7["OOS"], "IS_sharpe": res_mt7["IS"]["sharpe"]}
            results.append(r)
            oos = res_mt7["OOS"]
            print(f"  [MT7] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT7 error] {e}")
        results.append({"code": "MT7", "name": "短期イントラデイモメンタム(Gao2018)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # MT8: ファクターモメンタム
    try:
        mt8_sig_btc = strategy_MT8_factor_momentum(btc_p, btc_vol, fg_series)
        mt8_sig_eth = strategy_MT8_factor_momentum(eth_p, eth_vol, fg_series)
        res_mt8_btc = backtest_custom(btc_p, mt8_sig_btc, hold_days=14, stop=-0.08, take_profit=0.20, fee=0.001)
        res_mt8_eth = backtest_custom(eth_p, mt8_sig_eth, hold_days=14, stop=-0.08, take_profit=0.20, fee=0.001)
        for ticker, res_mt8 in [("BTC", res_mt8_btc), ("ETH", res_mt8_eth)]:
            r = {"code": "MT8", "name": "ファクターモメンタム(Arnott2021)", "ticker": ticker,
                 **res_mt8["OOS"], "IS_sharpe": res_mt8["IS"]["sharpe"]}
            results.append(r)
            oos = res_mt8["OOS"]
            print(f"  [MT8] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [MT8 error] {e}")
        results.append({"code": "MT8", "name": "ファクターモメンタム(Arnott2021)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ---- ME. 新モメンタム系（拡張3手法） ----
    print("\n[ME] 新モメンタム系（拡張3手法）")

    # ME1: アーニングスモメンタム（決算サプライズ）
    print("  [ME1] アーニングスモメンタム 取得中...")
    for ticker in ["NVDA", "ARM", "AAPL", "MSFT"]:
        try:
            me1_prices, me1_sig = strategy_ME1_earnings_momentum(ticker)
            if me1_prices is not None and me1_sig is not None and me1_sig.sum() > 0:
                res_me1 = backtest_custom(me1_prices, me1_sig, hold_days=60, stop=-0.10, take_profit=0.20, fee=0.001)
                r_me1 = {"code": "ME1", "name": "アーニングスモメンタム", "ticker": ticker,
                         **res_me1["OOS"], "IS_sharpe": res_me1["IS"]["sharpe"]}
                results.append(r_me1)
                oos = res_me1["OOS"]
                print(f"  [ME1] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                      f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
            else:
                print(f"  [ME1] {ticker} | シグナルなし → スキップ")
        except Exception as e:
            print(f"  [ME1 {ticker} error] {e}")
            results.append({"code": "ME1", "name": "アーニングスモメンタム", "ticker": ticker,
                            "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                            "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ME2: 債券×クリプト逆相関モメンタム（BTC, ETH）
    try:
        me2_sig_btc = strategy_ME2_bond_crypto_momentum(btc_p)
        me2_sig_eth = strategy_ME2_bond_crypto_momentum(eth_p)
        for ticker, prices_x, me2_sig in [("BTC", btc_p, me2_sig_btc), ("ETH", eth_p, me2_sig_eth)]:
            res_me2 = backtest_custom(prices_x, me2_sig, hold_days=30, stop=-0.10, take_profit=0.20, fee=0.001)
            r_me2 = {"code": "ME2", "name": "金利低下×BTC逆相関", "ticker": ticker,
                     **res_me2["OOS"], "IS_sharpe": res_me2["IS"]["sharpe"]}
            results.append(r_me2)
            oos = res_me2["OOS"]
            print(f"  [ME2] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [ME2 error] {e}")
        results.append({"code": "ME2", "name": "金利低下×BTC逆相関", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ME3: ML強化モメンタム（BTC, ETH）
    try:
        me3_sig_btc = strategy_ME3_ml_momentum(btc_p, btc_vol)
        me3_sig_eth = strategy_ME3_ml_momentum(eth_p, eth_vol)
        for ticker, prices_x, me3_sig in [("BTC", btc_p, me3_sig_btc), ("ETH", eth_p, me3_sig_eth)]:
            res_me3 = backtest_custom(prices_x, me3_sig, hold_days=5, stop=-0.05, take_profit=0.10, fee=0.001)
            r_me3 = {"code": "ME3", "name": "ML強化モメンタム(線形回帰)", "ticker": ticker,
                     **res_me3["OOS"], "IS_sharpe": res_me3["IS"]["sharpe"]}
            results.append(r_me3)
            oos = res_me3["OOS"]
            print(f"  [ME3] {ticker} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
    except Exception as e:
        print(f"  [ME3 error] {e}")
        results.append({"code": "ME3", "name": "ML強化モメンタム(線形回帰)", "ticker": "BTC",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ---- AC. 学術的資産配分戦略（7手法） ----
    print("\n[AC] 学術的資産配分戦略")

    # AC用データ取得
    print("  [AC] SOL/ARM データ取得中...")
    try:
        if 'sol_p' not in dir() or sol_p is None or len(sol_p) < 50:
            sol_full_ac = yf.download("SOL-USD", period="3y", auto_adjust=True, progress=False)
            sol_p_ac = sol_full_ac["Close"].dropna().squeeze() if not sol_full_ac.empty else None
        else:
            sol_p_ac = sol_p
    except Exception:
        sol_p_ac = None

    try:
        arm_full = yf.download("ARM", period="3y", auto_adjust=True, progress=False)
        arm_p = arm_full["Close"].dropna().squeeze() if not arm_full.empty else None
    except Exception:
        arm_p = None

    # AC1: 定期リバランス
    try:
        ac1_eq = strategy_AC1_rebalance()
        if ac1_eq is not None and len(ac1_eq) > 10:
            res_ac1 = backtest_portfolio_is_oos(ac1_eq)
            r_ac1 = {"code": "AC1", "name": "定期リバランス(Perold&Sharpe)", "ticker": "PORT",
                     **res_ac1["OOS"], "IS_sharpe": res_ac1["IS"]["sharpe"]}
            results.append(r_ac1)
            oos = res_ac1["OOS"]
            print(f"  [AC1] PORT | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        else:
            raise ValueError("insufficient data")
    except Exception as e:
        print(f"  [AC1 error] {e}")
        results.append({"code": "AC1", "name": "定期リバランス(Perold&Sharpe)", "ticker": "PORT",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC2: リスクパリティ
    try:
        ac2_eq = strategy_AC2_risk_parity()
        if ac2_eq is not None and len(ac2_eq) > 10:
            res_ac2 = backtest_portfolio_is_oos(ac2_eq)
            r_ac2 = {"code": "AC2", "name": "リスクパリティ(Qian)", "ticker": "PORT",
                     **res_ac2["OOS"], "IS_sharpe": res_ac2["IS"]["sharpe"]}
            results.append(r_ac2)
            oos = res_ac2["OOS"]
            print(f"  [AC2] PORT | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        else:
            raise ValueError("insufficient data")
    except Exception as e:
        print(f"  [AC2 error] {e}")
        results.append({"code": "AC2", "name": "リスクパリティ(Qian)", "ticker": "PORT",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC3: DCA効果検証 (BTC, ETH)
    for ticker_name, ticker_yf in [("BTC", "BTC-USD"), ("ETH", "ETH-USD")]:
        try:
            dca_eq, lump_eq = strategy_AC3_dca(ticker_yf)
            if dca_eq is not None and len(dca_eq) > 10:
                res_ac3 = backtest_portfolio_is_oos(dca_eq)
                r_ac3 = {"code": "AC3", "name": "DCA効果検証", "ticker": ticker_name,
                         **res_ac3["OOS"], "IS_sharpe": res_ac3["IS"]["sharpe"]}
                results.append(r_ac3)
                oos = res_ac3["OOS"]
                print(f"  [AC3] {ticker_name} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                      f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
            else:
                raise ValueError("insufficient data")
        except Exception as e:
            print(f"  [AC3 {ticker_name} error] {e}")
            results.append({"code": "AC3", "name": "DCA効果検証", "ticker": ticker_name,
                            "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                            "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC4: 低ボラティリティ戦略
    try:
        ac4_prices, ac4_eq = strategy_AC4_low_vol(btc_p, eth_p, sol_p_ac, arm_p)
        if ac4_eq is not None and len(ac4_eq) > 10:
            res_ac4 = backtest_portfolio_is_oos(ac4_eq)
            r_ac4 = {"code": "AC4", "name": "低ボラ選択(Frazzini&Pedersen)", "ticker": "PORT",
                     **res_ac4["OOS"], "IS_sharpe": res_ac4["IS"]["sharpe"]}
            results.append(r_ac4)
            oos = res_ac4["OOS"]
            print(f"  [AC4] PORT | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        else:
            raise ValueError("insufficient data")
    except Exception as e:
        print(f"  [AC4 error] {e}")
        results.append({"code": "AC4", "name": "低ボラ選択(Frazzini&Pedersen)", "ticker": "PORT",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC5: クリプトキャリー (BTC, ETH)
    for ticker_name, prices_x in [("BTC", btc_p), ("ETH", eth_p)]:
        try:
            ac5_sig = strategy_AC5_carry(prices_x)
            res_ac5 = backtest_custom(prices_x, ac5_sig, hold_days=30, stop=-0.10, take_profit=0.30, fee=0.001)
            r_ac5 = {"code": "AC5", "name": "クリプトキャリー(Lustig)", "ticker": ticker_name,
                     **res_ac5["OOS"], "IS_sharpe": res_ac5["IS"]["sharpe"]}
            results.append(r_ac5)
            oos = res_ac5["OOS"]
            print(f"  [AC5] {ticker_name} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        except Exception as e:
            print(f"  [AC5 {ticker_name} error] {e}")
            results.append({"code": "AC5", "name": "クリプトキャリー(Lustig)", "ticker": ticker_name,
                            "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                            "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC6: スマートベータ複合
    try:
        ac6_prices, ac6_eq = strategy_AC6_smart_beta(btc_p, eth_p, sol_p_ac, arm_p)
        if ac6_eq is not None and len(ac6_eq) > 10:
            res_ac6 = backtest_portfolio_is_oos(ac6_eq)
            r_ac6 = {"code": "AC6", "name": "スマートベータ複合(Arnott)", "ticker": "PORT",
                     **res_ac6["OOS"], "IS_sharpe": res_ac6["IS"]["sharpe"]}
            results.append(r_ac6)
            oos = res_ac6["OOS"]
            print(f"  [AC6] PORT | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        else:
            raise ValueError("insufficient data")
    except Exception as e:
        print(f"  [AC6 error] {e}")
        results.append({"code": "AC6", "name": "スマートベータ複合(Arnott)", "ticker": "PORT",
                        "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                        "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # AC7: マクロイベント逆張り (BTC, ETH)
    for ticker_name, prices_x in [("BTC", btc_p), ("ETH", eth_p)]:
        try:
            ac7_sig = strategy_AC7_event_driven(prices_x)
            res_ac7 = backtest_custom(prices_x, ac7_sig, hold_days=5, stop=-0.05, take_profit=0.10, fee=0.001)
            r_ac7 = {"code": "AC7", "name": "マクロイベント逆張り(B&B)", "ticker": ticker_name,
                     **res_ac7["OOS"], "IS_sharpe": res_ac7["IS"]["sharpe"]}
            results.append(r_ac7)
            oos = res_ac7["OOS"]
            print(f"  [AC7] {ticker_name} | Sharpe={oos['sharpe']:+.2f} | Ret={oos['total_return']:+.0f}% | "
                  f"MDD={oos['mdd']:.0f}% | Win={oos['win_rate']:.0f}% | p={oos['pvalue']:.3f} | T={oos['trades']}")
        except Exception as e:
            print(f"  [AC7 {ticker_name} error] {e}")
            results.append({"code": "AC7", "name": "マクロイベント逆張り(B&B)", "ticker": ticker_name,
                            "sharpe": 0, "total_return": 0, "pvalue": 1.0, "mdd": 0,
                            "win_rate": 0, "trades": 0, "IS_sharpe": 0})

    # ============================================================
    # ランキング作成 & 保存
    # ============================================================

    df = pd.DataFrame(results)
    # スコア: Sharpe * (1-pvalue) * (1-|mdd|/100)
    df["score"] = (
        df["sharpe"].clip(lower=-5)
        * (1 - df["pvalue"].clip(0, 1))
        * (1 - df["mdd"].abs() / 100)
    )
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # 100点満点スコアとシグナルを付与
    df["total_score_100"] = df.apply(lambda row: calc_total_score(row.to_dict()), axis=1)
    df["signal_color"] = df["total_score_100"].apply(get_signal_color)
    df["signal_label"] = df["total_score_100"].apply(get_signal_label)

    # スコアでソートした別ビュー（上位10件をスコアランキングに使う）
    df_score_ranked = df.sort_values("total_score_100", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 60)
    print("OOS ランキング TOP 10")
    print("=" * 60)
    cols = ["rank", "code", "name", "ticker", "sharpe", "total_return", "mdd", "win_rate", "pvalue", "trades", "score"]
    print(df[cols].head(10).to_string(index=False))

    # JSON保存
    out = {
        "generated_at": datetime.now().isoformat(),
        "ranking": df.to_dict("records"),
        "score_ranking": df_score_ranked[["code", "name", "ticker", "total_score_100", "signal_color", "signal_label", "sharpe", "total_return", "pvalue", "mdd", "trades"]].to_dict("records"),
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n結果保存: {OUT_FILE}")

    # ============================================================
    # Telegram 3分割送信
    # ============================================================
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # メッセージ1: TOP10
    top10_lines = []
    for _, row in df.head(10).iterrows():
        top10_lines.append(
            f"{row['rank']}. [{row['code']}] {row['name']} ({row['ticker']}) "
            f"| Sharpe={row['sharpe']:+.2f} | Ret={row['total_return']:+.0f}% "
            f"| Win={row['win_rate']:.0f}% | p={row['pvalue']:.3f}"
        )
    msg1 = f"<b>🏆 全手法OOSランキング TOP10 [{now_str}]</b>\n\n" + "\n".join(top10_lines)
    tg(msg1)
    time.sleep(1)

    # メッセージ2: 中位 11-20
    mid_lines = []
    for _, row in df.iloc[10:20].iterrows():
        mid_lines.append(
            f"{row['rank']}. [{row['code']}] {row['name']} ({row['ticker']}) "
            f"| Sharpe={row['sharpe']:+.2f} | Ret={row['total_return']:+.0f}%"
        )
    msg2 = "<b>📊 11〜20位</b>\n\n" + "\n".join(mid_lines) if mid_lines else ""
    if msg2:
        tg(msg2)
        time.sleep(1)

    # メッセージ3: ワースト5 + 統計サマリー
    worst_lines = []
    for _, row in df.tail(5).iterrows():
        worst_lines.append(
            f"{row['rank']}. [{row['code']}] {row['name']} ({row['ticker']}) "
            f"| Sharpe={row['sharpe']:+.2f} | MDD={row['mdd']:.0f}%"
        )
    n_pos     = (df["sharpe"] > 0).sum()
    n_sig     = (df["pvalue"] < 0.05).sum()
    best_row  = df.iloc[0]
    msg3 = (
        f"<b>⚠️ ワースト5</b>\n" + "\n".join(worst_lines) +
        f"\n\n<b>📈 統計サマリー</b>\n"
        f"総手法数: {len(df)}\n"
        f"Sharpe>0: {n_pos}/{len(df)}\n"
        f"p<0.05(有意): {n_sig}/{len(df)}\n"
        f"最強: [{best_row['code']}] {best_row['name']} ({best_row['ticker']}) "
        f"Sharpe={best_row['sharpe']:+.2f}"
    )
    tg(msg3)
    time.sleep(1)

    # メッセージ4: 戦略スコアランキング（100点満点）
    score_lines = []
    for _, row in df_score_ranked.head(10).iterrows():
        sc = int(row['total_score_100'])
        color = row['signal_color']
        label = row['signal_label']
        label_emoji = "✅" if sc >= 80 else ("⚠️" if sc >= 50 else "❌")
        score_lines.append(
            f"{color} [{row['code']}] {row['name']}({row['ticker']})  {sc}点 {label_emoji}{label}\n"
            f"   Sharpe={row['sharpe']:+.2f} リターン{row['total_return']:+.0f}% "
            f"p={row['pvalue']:.3f} DD={row['mdd']:.0f}%"
        )
    msg4 = "<b>⚛️ 戦略スコアランキング（100点満点）</b>\n\n" + "\n\n".join(score_lines)
    tg(msg4)

    print("\n✅ Telegram送信完了")
    print(f"✅ 全{len(df)}手法 検証完了")


if __name__ == "__main__":
    run_all()
