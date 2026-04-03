"""
&AI QUANTUM EDGE — TimesFM 予測モジュール
Google Research TimesFM 2.5を使って価格予測を生成

使い方:
  from timesfm_predictor import predict_prices, predict_all_assets
  
  # 単一銘柄
  result = predict_prices("BTC", horizon=7)
  
  # 全銘柄一括
  results = predict_all_assets(horizon=7)
"""

import os
import sys
import json
import numpy as np
import requests
from datetime import datetime, timedelta

# TimesFM用venv
TIMESFM_VENV = os.path.expanduser("~/remote-workspace/timesfm-env/.venv")

def _ensure_timesfm():
    """TimesFMモデルをロード（キャッシュ）"""
    global _model, _loaded
    if '_loaded' in globals() and _loaded:
        return _model
    
    # venvのパスを追加
    site_packages = os.path.join(TIMESFM_VENV, "lib")
    for d in os.listdir(site_packages):
        sp = os.path.join(site_packages, d, "site-packages")
        if os.path.exists(sp) and sp not in sys.path:
            sys.path.insert(0, sp)
    
    import torch
    import timesfm
    
    torch.set_float32_matmul_precision("high")
    
    print("[TimesFM] Loading model...")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        "google/timesfm-2.5-200m-pytorch"
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=1024,
            max_horizon=60,
            normalize_inputs=True,
            use_continuous_quantile_head=True,
            force_flip_invariance=True,
            infer_is_positive=True,
            fix_quantile_crossing=True,
        )
    )
    print("[TimesFM] Model ready.")
    
    _model = model
    _loaded = True
    return model


def get_historical_prices(symbol: str, days: int = 365) -> list:
    """
    過去の価格データを取得
    
    対応:
    - BTC, ETH等 → CoinGecko API（無料）
    - SPY, EFA, GLD, BIL等 → yfinance
    """
    symbol_upper = symbol.upper()
    
    # 暗号資産
    crypto_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum", 
        "SOL": "solana",
        "BNB": "binancecoin",
    }
    
    if symbol_upper in crypto_map:
        cg_id = crypto_map[symbol_upper]
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        prices = [p[1] for p in data["prices"]]
        return prices
    
    # 株式/ETF → yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol_upper)
        hist = ticker.history(period=f"{days}d")
        return hist["Close"].tolist()
    except ImportError:
        # yfinanceなければAlpha Vantage等のフォールバック
        print(f"[TimesFM] yfinance not available for {symbol}")
        return []


def predict_prices(
    symbol: str,
    horizon: int = 7,
    history_days: int = 365,
    confidence_levels: list = None
) -> dict:
    """
    指定銘柄の価格予測
    
    Args:
        symbol: 銘柄（BTC, ETH, SPY, EFA等）
        horizon: 何日先まで予測するか
        history_days: 過去何日分のデータを使うか
        confidence_levels: 信頼区間（デフォルト: 10%, 50%, 90%）
    
    Returns:
        {
            "symbol": "BTC",
            "current_price": 68500.0,
            "horizon": 7,
            "predictions": [
                {"day": 1, "point": 68800, "low_10": 67500, "high_90": 70100},
                ...
            ],
            "trend": "bullish" | "bearish" | "neutral",
            "confidence": 0.75,
            "predicted_7d_change_pct": 2.3,
            "timestamp": "2026-04-02T19:00:00"
        }
    """
    model = _ensure_timesfm()
    
    # 過去データ取得
    prices = get_historical_prices(symbol, history_days)
    if len(prices) < 30:
        return {"error": f"Insufficient data for {symbol}: {len(prices)} points"}
    
    current_price = prices[-1]
    
    # TimesFM予測
    input_array = np.array(prices)
    point_forecast, quantile_forecast = model.forecast(
        horizon=horizon,
        inputs=[input_array],
    )
    
    # 結果整形
    predictions = []
    for i in range(horizon):
        pred = {
            "day": i + 1,
            "point": round(float(point_forecast[0][i]), 2),
        }
        if quantile_forecast is not None and len(quantile_forecast.shape) == 3:
            # quantile_forecast shape: (1, horizon, num_quantiles)
            # Default quantiles: mean, 10th, 20th, ..., 90th
            q = quantile_forecast[0][i]
            pred["low_10"] = round(float(q[0]), 2)   # 10th percentile
            pred["median"] = round(float(q[4]), 2)    # 50th percentile  
            pred["high_90"] = round(float(q[-1]), 2)  # 90th percentile
        predictions.append(pred)
    
    # トレンド判定
    predicted_end = float(point_forecast[0][-1])
    change_pct = ((predicted_end - current_price) / current_price) * 100
    
    if change_pct > 2:
        trend = "bullish"
    elif change_pct < -2:
        trend = "bearish"
    else:
        trend = "neutral"
    
    # 信頼度（予測のばらつきから算出）
    if quantile_forecast is not None and len(quantile_forecast.shape) == 3:
        spreads = quantile_forecast[0][:, -1] - quantile_forecast[0][:, 0]
        avg_spread_pct = float(np.mean(spreads) / current_price * 100)
        confidence = max(0.1, min(0.99, 1 - avg_spread_pct / 20))
    else:
        confidence = 0.5
    
    return {
        "symbol": symbol.upper(),
        "current_price": round(current_price, 2),
        "horizon": horizon,
        "predictions": predictions,
        "trend": trend,
        "confidence": round(confidence, 3),
        "predicted_change_pct": round(change_pct, 2),
        "timestamp": datetime.now().isoformat(),
        "model": "TimesFM 2.5 (200M)",
    }


def predict_all_assets(horizon: int = 7) -> dict:
    """
    QEの全対象銘柄を一括予測
    
    Returns:
        {
            "BTC": {...prediction...},
            "ETH": {...prediction...},
            "SPY": {...prediction...},
            ...
        }
    """
    # QE対象銘柄
    assets = ["BTC", "ETH", "SPY", "EFA", "GLD"]
    
    results = {}
    for symbol in assets:
        try:
            print(f"[TimesFM] Predicting {symbol}...")
            results[symbol] = predict_prices(symbol, horizon=horizon)
        except Exception as e:
            results[symbol] = {"error": str(e)}
    
    return results


def generate_telegram_report(results: dict) -> str:
    """
    Telegram用のレポート文字列を生成
    """
    lines = [
        f"TimesFM Price Forecast",
        f"{datetime.now().strftime('%Y/%m/%d %H:%M')}",
        f"Model: TimesFM 2.5 (Google Research)",
        "",
    ]
    
    for symbol, data in results.items():
        if "error" in data:
            lines.append(f"{symbol}: Error - {data['error']}")
            continue
        
        trend_icon = {"bullish": "+", "bearish": "-", "neutral": "="}
        t = trend_icon.get(data["trend"], "?")
        
        lines.append(f"{symbol} | Now: ${data['current_price']:,.2f}")
        lines.append(f"  7d Forecast: {t}{data['predicted_change_pct']:+.1f}%")
        lines.append(f"  Confidence: {data['confidence']:.0%}")
        
        if data["predictions"]:
            p7 = data["predictions"][-1]
            lines.append(f"  Target: ${p7['point']:,.2f}")
            if "low_10" in p7 and "high_90" in p7:
                lines.append(f"  Range: ${p7['low_10']:,.2f} - ${p7['high_90']:,.2f}")
        lines.append("")
    
    return "\n".join(lines)


# === CLI テスト ===
if __name__ == "__main__":
    print("=== TimesFM Predictor Test ===\n")
    
    # BTC予測テスト
    result = predict_prices("BTC", horizon=7)
    
    if "error" not in result:
        print(f"Symbol: {result['symbol']}")
        print(f"Current: ${result['current_price']:,.2f}")
        print(f"Trend: {result['trend']}")
        print(f"7d Change: {result['predicted_change_pct']:+.1f}%")
        print(f"Confidence: {result['confidence']:.0%}")
        print(f"\nDay-by-day:")
        for p in result['predictions']:
            low = f"${p.get('low_10', 0):,.0f}" if 'low_10' in p else "N/A"
            high = f"${p.get('high_90', 0):,.0f}" if 'high_90' in p else "N/A"
            print(f"  Day {p['day']}: ${p['point']:,.0f} ({low} - {high})")
    else:
        print(f"Error: {result['error']}")
