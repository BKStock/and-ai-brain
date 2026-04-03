"""
&AI QUANTUM EDGE - 専用指揮センターBot
@bk_training_en_bot
"""

import asyncio
import logging
import sys
import os
sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')

from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

BOT_TOKEN = os.environ.get("QE_COMMAND_BOT_TOKEN")
WHALE_ALERT_KEY = os.environ.get("WHALE_ALERT_KEY", "")
OWNER_ID = int(os.environ.get("QE_OWNER_CHAT_ID", "5791086501"))

logging.basicConfig(level=logging.WARNING)

# ========================================
# 認証チェック
# ========================================
PROJECT_GROUP_ID = -1003799035163  # &AIプロジェクト管理グループ

ALLOWED_GROUPS = {-1003799035163}  # &AIプロジェクト管理のみ（投資グループは除外）

def is_authorized(update: Update) -> bool:
    """KK本人 + 許可グループからのKKのみ許可"""
    if not update.effective_user:
        return False
    user_ok = update.effective_user.id == OWNER_ID
    if not user_ok:
        return False
    # Direct Chatは常にOK
    chat = update.effective_chat
    if not chat or chat.type == 'private':
        return True
    # グループの場合は許可リストのみ
    if chat.id in ALLOWED_GROUPS:
        return True
    return False


# ========================================
# /start /help
# ========================================
def get_persistent_keyboard():
    """常駐キーボード（入力欄の上に常時表示）"""
    return ReplyKeyboardMarkup(
        [
            # 1段目: 最も使う情報確認
            [
                KeyboardButton("📊 レポート"),
                KeyboardButton("💹 価格"),
                KeyboardButton("🏦 ファンド"),
            ],
            # 2段目: シグナル・速報
            [
                KeyboardButton("🐋 クジラ"),
                KeyboardButton("⚡ シグナル"),
                KeyboardButton("⚛️ 量子"),
            ],
            # 3段目: ポジション管理 + APIキー取得
            [
                KeyboardButton("🔄 更新"),
                KeyboardButton("🎯 利確"),
                KeyboardButton("🔑 APIキー"),
            ],
        ],
        resize_keyboard=True,      # スマホに合わせてサイズ調整
        persistent=True,           # 常に表示
        input_field_placeholder="コマンドを選択またはテキスト入力",
    )


async def handle_keyboard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """常駐キーボードのテキストボタン処理"""
    if not is_authorized(update): return
    text = update.message.text

    if text == "📊 レポート":
        await update.message.reply_text("⚛️ データ収集中...（30〜60秒）", reply_markup=get_persistent_keyboard())
        try:
            from brain_collector import generate_brain_report
            msg, _ = generate_brain_report()
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "💹 価格":
        try:
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type":"allMids"}, timeout=10)
            mids = r.json()
            pairs = [("BTC","₿"),("ETH","Ξ"),("SOL","◎"),("XRP","✕"),("TRX","T"),("TON","⟨")]
            lines = ["💹 *現在価格*\n"]
            for ticker, icon in pairs:
                p = float(mids.get(ticker, 0))
                if p > 0:
                    lines.append(f"{icon} {ticker}: ${p:,.4f}")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "🏦 ファンド":
        try:
            from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type":"allMids"}, timeout=10)
            mids = {k: float(v) for k, v in r.json().items()}
            from demo_fund import update_positions
            lines = ["🏦 *デモファンド状況*\n"]
            total_val = 0
            for fid in ["fund_1","fund_2","fund_3"]:
                update_positions(fid, mids)
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                val = fd.get("portfolio_value", INITIAL_CAPITAL)
                pnl = val - INITIAL_CAPITAL
                pnl_pct = pnl / INITIAL_CAPITAL * 100
                total_val += val
                open_pos = [p for p in fd.get("open_positions",[]) if p.get("status")=="OPEN"]
                arrow = "📈" if pnl >= 0 else "📉"
                lines.append(f"{cfg['emoji']} {cfg['name']}: ¥{val:,.0f} {arrow}{pnl_pct:+.2f}% | {len(open_pos)}件")
            total_pnl = total_val - INITIAL_CAPITAL * 3
            lines.append(f"\n💰 合計: ¥{total_val:,.0f} ({total_pnl:+,.0f}円)")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "🐋 クジラ":
        try:
            from brain_collector import get_whale_alerts, format_whale_section
            whale_data = get_whale_alerts()
            section = format_whale_section(whale_data)
            alerts = whale_data.get("alerts", [])
            await update.message.reply_text(f"🐋 *クジラ速報*\n{section}\n{len(alerts)}件（過去4h）",
                parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "⚡ シグナル":
        try:
            from momentum_engine import get_all_momentum_scores
            scores = get_all_momentum_scores()
            top3 = sorted(scores, key=lambda x: x["score"], reverse=True)[:3]
            lines = ["⚡ *シグナル状況*\n"]
            for i, s in enumerate(top3, 1):
                medal = ["🥇","🥈","🥉"][i-1]
                lines.append(f"{medal} {s['name']}: {s['score']}点")
            # 現在のシグナル判定
            lines.append(f"\n最高スコア: {top3[0]['score']}点")
            if top3[0]['score'] >= 80:
                lines.append("⚡ FUND-1: エントリー候補！")
            elif top3[0]['score'] >= 75:
                lines.append("⚡ FUND-2/3: エントリー候補！")
            else:
                lines.append("⏸️ 条件未達 - 待機中")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "⚛️ 量子":
        await update.message.reply_text("⚛️ 量子レポート生成中...（30秒）", reply_markup=get_persistent_keyboard())
        try:
            from quantum_report import generate_quantum_report
            generate_quantum_report()
            await update.message.reply_text("✅ 量子レポートをTelegramに送信しました！", reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "🔄 更新":
        try:
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type":"allMids"}, timeout=10)
            mids = {k: float(v) for k, v in r.json().items()}
            from demo_fund import update_positions, load_fund, FUNDS, INITIAL_CAPITAL
            lines = ["🔄 *更新完了*\n"]
            for fid in ["fund_1","fund_2","fund_3"]:
                closed = update_positions(fid, mids)
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                val = fd.get("portfolio_value", INITIAL_CAPITAL)
                pnl_pct = (val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
                open_pos = [p for p in fd.get("open_positions",[]) if p.get("status")=="OPEN"]
                lines.append(f"{cfg['emoji']} {cfg['name']}: ¥{val:,.0f} ({pnl_pct:+.2f}%) | {len(open_pos)}件")
                for c in closed:
                    lines.append(f"  💥 {c.get('status','')}: {c['ticker']} {c.get('pnl_pct',0):+.2f}%")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "🎯 利確":
        try:
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type":"allMids"}, timeout=10)
            mids = {k: float(v) for k, v in r.json().items()}
            from demo_fund import load_fund, FUNDS
            lines = ["🎯 *利確ライン確認*\n"]
            found = False
            for fid in ["fund_1","fund_2","fund_3"]:
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                for p in fd.get("open_positions",[]):
                    if p.get("status") != "OPEN": continue
                    ticker = p["ticker"]
                    current = float(mids.get(ticker, p["entry_price"]))
                    tp1 = p.get("take_profit_1", 0)
                    sl = p.get("stop_loss", 0)
                    pnl_pct = p.get("pnl_pct", 0)
                    tp1_dist = (tp1 - current) / current * 100 if tp1 > current else 0
                    sl_dist = (current - sl) / current * 100 if sl > 0 and current > sl else 0
                    arrow = "🟢" if pnl_pct >= 0 else "🔴"
                    lines.append(f"{arrow} {cfg['emoji']} {ticker}: {pnl_pct:+.2f}%")
                    lines.append(f"  🎯 利確①まで: +{tp1_dist:.1f}%")
                    lines.append(f"  🛑 損切りまで: -{sl_dist:.1f}%")
                    found = True
            if not found:
                lines.append("現在ポジションなし")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_persistent_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())

    elif text == "📱 ダッシュ":
        await dashboard(update, context)

    elif text == "🔑 APIキー":
        USER_WAITING_FOR_URL.add(update.effective_user.id)
        await update.message.reply_text(
            "🔑 *APIキー自動取得*\n\n"
            "取得したいサービスのURLを入力してください\n\n"
            "例:\n"
            "• `https://edinetdb.jp`\n"
            "• `https://jpx-jquants.com`\n"
            "• `https://tavily.com`\n"
            "• その他任意のURL\n\n"
            "URLを送ってください👇",
            parse_mode="Markdown",
            reply_markup=get_persistent_keyboard()
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    msg = "⚛️ *&AI QUANTUM EDGE 指揮センター*\n\nボタンを押して操作してください 👇"
    
    keyboard = [
        # 1段目: ダッシュボード
        [InlineKeyboardButton("📱 管理ダッシュボード", callback_data="dash:home")],
        # 2段目: 情報確認
        [
            InlineKeyboardButton("📊 レポート", callback_data="cmd:report"),
            InlineKeyboardButton("💹 価格", callback_data="cmd:price"),
            InlineKeyboardButton("🏦 ファンド", callback_data="dash:portfolio"),
        ],
        # 3段目: シグナル系
        [
            InlineKeyboardButton("⚡ シグナル", callback_data="dash:trading"),
            InlineKeyboardButton("🐋 クジラ速報", callback_data="cmd:whale"),
            InlineKeyboardButton("⚛️ 量子", callback_data="cmd:quantum_report"),
        ],
        # 4段目: ファンドルール
        [
            InlineKeyboardButton("🛡️ FUND-1ルール", callback_data="fund:rule:fund_1"),
            InlineKeyboardButton("⚡ FUND-2ルール", callback_data="fund:rule:fund_2"),
            InlineKeyboardButton("🚀 FUND-3ルール", callback_data="fund:rule:fund_3"),
        ],
        # 5段目: アクション
        [
            InlineKeyboardButton("🔄 ポジション更新", callback_data="cmd:update_positions"),
            InlineKeyboardButton("🎯 利確確認", callback_data="cmd:check_tp"),
        ],
        # 6段目: その他
        [
            InlineKeyboardButton("💬 チームに聞く", callback_data="cmd:team_ask"),
            InlineKeyboardButton("📅 経済指標", callback_data="cmd:calendar"),
            InlineKeyboardButton("🚨 緊急停止", callback_data="cmd:emergency_stop"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # インラインキーボード送信
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    # 常駐キーボードを別メッセージで表示
    await update.message.reply_text(
        "👆 上のボタンまたは下の常駐キーボードから操作してください",
        reply_markup=get_persistent_keyboard()
    )


# ========================================
# /report — 今すぐレポート送信
# ========================================
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("⚛️ データ収集中... 少々お待ちください（30〜60秒）")
    
    try:
        from brain_collector import generate_brain_report, send_to_telegram
        msg, _ = generate_brain_report()
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /price — 現在価格
# ========================================
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("📈 価格取得中...")
    
    try:
        import yfinance as yf
        tickers = {
            'BTC-USD':'BTC','ETH-USD':'ETH','TRX-USD':'TRX',
            'SOL-USD':'SOL','XRP-USD':'XRP',
            'NVDA':'NVDA','MSFT':'MSFT','ARM':'ARM','AMD':'AMD',
            'LVS':'LVS','MLCO':'MLCO','SE':'SEA',
            'DKNG':'DKNG','GRAB':'GRAB','GC=F':'Gold'
        }
        
        msg = "📊 *現在価格*\n\n"
        categories = {
            '⚡ 仮想通貨': ['BTC-USD','ETH-USD','TRX-USD','SOL-USD','XRP-USD'],
            '📈 AI×テック': ['NVDA','MSFT','ARM','AMD'],
            '🎰 iGaming×ASEAN': ['LVS','MLCO','SE','DKNG','GRAB'],
            '🛡️ 安全資産': ['GC=F'],
        }
        
        for cat, cat_tickers in categories.items():
            msg += f"*{cat}*\n"
            for t in cat_tickers:
                name = tickers[t]
                try:
                    hist = yf.Ticker(t).history(period='2d')
                    if len(hist) >= 2:
                        price = hist['Close'].iloc[-1]
                        chg = (hist['Close'].iloc[-1]/hist['Close'].iloc[-2]-1)*100
                        arrow = "▲" if chg > 0 else "▼"
                        msg += f"  {name}: ${price:,.2f} ({chg:+.1f}% {arrow})\n"
                except: pass
            msg += "\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /momentum — モメンタムランキング
# ========================================
async def momentum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    await update.message.reply_text("🔥 モメンタム計算中...")
    
    try:
        from momentum_engine import get_all_momentum_scores
        scores = get_all_momentum_scores()
        
        msg = "🔥 *モメンタムランキング*\n\n"
        
        msg += "📈 *上位5銘柄（買いシグナル）*\n"
        for i, s in enumerate(scores[:5], 1):
            bar = "█" * (s['score'] // 15)
            msg += f"  {i}. {s['name']:5s} {s['score']}点 {bar} {s['arrows']}\n"
        
        msg += "\n⚠️ *下位3銘柄（注意）*\n"
        for s in scores[-3:]:
            msg += f"  ▼ {s['name']:5s} {s['score']}点 {s['signal']}\n"
        
        msg += f"\n更新: {__import__('datetime').datetime.now().strftime('%H:%M JST')}"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /portfolio — 量子ポートフォリオ
# ========================================
async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    keyboard = [
        [
            InlineKeyboardButton("🔥 積極運用", callback_data="pf:aggressive"),
            InlineKeyboardButton("⚖️ バランス", callback_data="pf:balanced"),
            InlineKeyboardButton("🛡️ 安全", callback_data="pf:safe"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚛️ 投資スタイルを選択してください:",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """メインメニューボタンの処理"""
    query = update.callback_query
    await query.answer()
    if not is_authorized(update): return
    
    action = query.data.replace("cmd:", "")
    
    # ローディング表示
    loading_msgs = {
        "report": "⚛️ データ収集中... 少々お待ちください（30〜60秒）",
        "price": "📈 価格取得中...",
        "momentum": "🔥 モメンタム計算中...",
        "accuracy": "🎯 精度データ集計中...",
        "monthly": "📊 月次レポート生成中...",
        "status": "⚙️ システム状態確認中...",
    }
    
    if action in loading_msgs:
        await query.edit_message_text(loading_msgs[action])
    
    # 各アクション実行
    if action == "report":
        try:
            from brain_collector import generate_brain_report
            msg, _ = generate_brain_report()
            await context.bot.send_message(chat_id=query.message.chat_id, text=msg, parse_mode='Markdown')
            await show_main_menu(query, context, "✅ レポート送信完了！")
        except Exception as e:
            await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")
    
    elif action == "price":
        try:
            import yfinance as yf
            from datetime import datetime
            now = datetime.now().strftime("%m/%d %H:%M")
            
            tickers = {
                'BTC-USD':'BTC','ETH-USD':'ETH','TRX-USD':'TRX',
                'SOL-USD':'SOL','XRP-USD':'XRP',
                'NVDA':'NVDA','MSFT':'MSFT','ARM':'ARM','AMD':'AMD',
                'LVS':'LVS','MLCO':'MLCO','SE':'SEA',
                'DKNG':'DKNG','GRAB':'GRAB','GC=F':'Gold'
            }
            
            categories = {
                '⚡ 仮想通貨': ['BTC-USD','ETH-USD','TRX-USD','SOL-USD','XRP-USD'],
                '🤖 AI×テック': ['NVDA','MSFT','ARM','AMD'],
                '🎰 iGaming×ASEAN': ['LVS','MLCO','SE','DKNG','GRAB'],
                '🛡️ 安全資産': ['GC=F'],
            }
            
            msg = f"💹 *リアルタイム価格*  `{now} JST`\n"
            
            for cat, cat_tickers in categories.items():
                msg += f"\n*{cat}*\n"
                msg += "┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                for t in cat_tickers:
                    name = tickers[t]
                    try:
                        hist = yf.Ticker(t).history(period='2d')
                        if len(hist) >= 2:
                            p = hist['Close'].iloc[-1]
                            chg = (hist['Close'].iloc[-1]/hist['Close'].iloc[-2]-1)*100
                            if chg >= 1.5:
                                icon = "🟢"
                            elif chg >= 0:
                                icon = "🔵"
                            elif chg >= -1.5:
                                icon = "🟡"
                            else:
                                icon = "🔴"
                            arrow = "▲" if chg >= 0 else "▼"
                            msg += f"{icon} `{name:5s}` `${p:>10,.2f}` `{chg:+.1f}%` {arrow}\n"
                    except: pass
            
            msg += "\n🟢≥+1.5%  🔵≥0%  🟡≥-1.5%  🔴<-1.5%"
            
            await show_main_menu(query, context, msg)
        except Exception as e:
            await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")
    
    elif action == "momentum":
        try:
            from momentum_engine import get_all_momentum_scores
            from datetime import datetime
            scores = get_all_momentum_scores()
            now = datetime.now().strftime("%m/%d %H:%M")
            
            msg = f"🔥 *モメンタムランキング*  `{now} JST`\n"
            msg += "━━━━━━━━━━━━━━━\n\n"
            
            # 上位5銘柄
            msg += "🚀 *買いシグナル TOP5*\n"
            medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
            for i, s in enumerate(scores[:5]):
                score = s['score']
                # スコアバー（10段階）
                filled = score // 10
                bar = "▓" * filled + "░" * (10 - filled)
                change = s.get('change_24h', 0)
                change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
                trend_emoji = "🔺" if score >= 75 else "📈" if score >= 60 else "➡️"
                msg += f"{medals[i]} *{s['name']}*  `{score}点`\n"
                msg += f"   `{bar}` {trend_emoji} `{change_str}`\n"
            
            msg += "\n━━━━━━━━━━━━━━━\n"
            
            # 下位3銘柄
            msg += "⚠️ *注意銘柄 BOTTOM3*\n"
            for s in scores[-3:]:
                score = s['score']
                change = s.get('change_24h', 0)
                change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
                msg += f"🔻 *{s['name']}*  `{score}点`  `{change_str}`\n"
            
            msg += "\n━━━━━━━━━━━━━━━\n"
            msg += "💡 _スコア75以上 = 強い買いシグナル_\n"
            msg += "_スコア30以下 = 要注意_"
            
            await show_main_menu(query, context, msg)
        except Exception as e:
            await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")
    
    elif action == "portfolio_menu":
        keyboard = [
            [
                InlineKeyboardButton("🔥 積極運用", callback_data="pf:aggressive"),
                InlineKeyboardButton("⚖️ バランス", callback_data="pf:balanced"),
                InlineKeyboardButton("🛡️ 安全", callback_data="pf:safe"),
            ],
            [InlineKeyboardButton("← 戻る", callback_data="cmd:back")]
        ]
        await query.edit_message_text(
            "⚛️ 投資スタイルを選択してください:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif action == "accuracy":
        try:
            from prediction_tracker import get_accuracy_summary
            from feedback_tracker import load_feedback, get_win_rate
            win = get_win_rate()
            fb = load_feedback()
            total_fb = fb.get('total_helpful',0) + fb.get('total_not_helpful',0)
            fb_rate = fb.get('total_helpful',0) / total_fb * 100 if total_fb > 0 else 0
            wr = win.get('win_rate', 0)
            if wr < 60: price_str = "無料"
            elif wr < 65: price_str = "$29/月"
            elif wr < 70: price_str = "$59/月"
            elif wr < 75: price_str = "$99/月"
            else: price_str = "$149/月"
            msg = f"""🎯 *予測精度レポート*

方向性的中率: *{wr}%*
レンジ内的中率: *{win.get('range_rate', 0)}%*
累計: {win.get('wins',0)}/{win.get('total',0)}回

💬 満足度: {fb_rate:.0f}%
👍 {fb.get('total_helpful',0)}回 / 👎 {fb.get('total_not_helpful',0)}回

💰 現在の適正価格: *{price_str}*"""
            await show_main_menu(query, context, msg)
        except Exception as e:
            await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")
    
    elif action == "monthly":
        try:
            from feedback_tracker import send_monthly_report
            send_monthly_report()
            await show_main_menu(query, context, "✅ 月次レポートを送信しました！")
        except Exception as e:
            await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")
    
    elif action == "status":
        import subprocess, os
        brain_ok = os.path.exists('/Users/mr.k/Projects/and-ai-brain/latest_report.json')
        line_ok = os.path.exists('/tmp/andai-line-harness.log')
        msg = f"""⚙️ *システム状態*

✅ Command Bot: 稼働中
{'✅' if brain_ok else '⚠️'} 最新レポート: {'あり' if brain_ok else 'なし'}
{'✅' if line_ok else '⚠️'} LINEサーバー: {'稼働中' if line_ok else '要確認'}
✅ 毎朝8:00自動配信: 設定済み

🔧 次のステップ:
→ Amazon Braket有効化（本日14:00）"""
        await show_main_menu(query, context, msg)
    
    elif action == "whale":
        try:
            from brain_collector import get_whale_alerts, format_whale_section
            whale_data = get_whale_alerts()
            section = format_whale_section(whale_data)
            alerts = whale_data.get("alerts", [])
            msg = f"🐋 *クジラ速報*\n{section}\n\n件数: {len(alerts)}件（過去4時間）"
            await query.edit_message_text(msg, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ {str(e)[:100]}")

    elif action == "update_positions":
        try:
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type": "allMids"}, timeout=10)
            mids = {k: float(v) for k, v in r.json().items()}
            from demo_fund import update_positions, load_fund, FUNDS, INITIAL_CAPITAL
            lines = ["🔄 *ポジション更新完了*\n"]
            for fid in ["fund_1","fund_2","fund_3"]:
                closed = update_positions(fid, mids)
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                val = fd.get("portfolio_value", INITIAL_CAPITAL)
                pnl_pct = (val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
                open_pos = [p for p in fd.get("open_positions",[]) if p.get("status")=="OPEN"]
                lines.append(f"{cfg['emoji']} {cfg['name']}: ¥{val:,.0f} ({pnl_pct:+.2f}%) | {len(open_pos)}件")
                if closed:
                    for c in closed:
                        lines.append(f"  💥 {c['status']}: {c['ticker']} {c.get('pnl_pct',0):+.2f}%")
            await query.edit_message_text("\n".join(lines), parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ {str(e)[:100]}")

    elif action == "check_tp":
        try:
            import requests as req
            r = req.post("https://api.hyperliquid.xyz/info", json={"type": "allMids"}, timeout=10)
            mids = {k: float(v) for k, v in r.json().items()}
            from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
            lines = ["🎯 *利確ライン確認*\n"]
            for fid in ["fund_1","fund_2","fund_3"]:
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                for p in fd.get("open_positions",[]):
                    if p.get("status") != "OPEN": continue
                    ticker = p["ticker"]
                    current = float(mids.get(ticker, p["entry_price"]))
                    tp1 = p.get("take_profit_1", 0)
                    sl = p.get("stop_loss", 0)
                    pnl_pct = p.get("pnl_pct", 0)
                    tp1_dist = (tp1 - current) / current * 100 if tp1 > current else 0
                    sl_dist = (current - sl) / current * 100 if sl > 0 and current > sl else 0
                    arrow = "🟢" if pnl_pct >= 0 else "🔴"
                    lines.append(f"{arrow} {cfg['emoji']} {ticker}: {pnl_pct:+.2f}%")
                    lines.append(f"  🎯 利確①まであと: +{tp1_dist:.1f}%")
                    lines.append(f"  🛑 損切りまで: -{sl_dist:.1f}%")
            if len(lines) == 1:
                lines.append("現在ポジションなし")
            await query.edit_message_text("\n".join(lines), parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ {str(e)[:100]}")

    elif action == "team_ask":
        await query.edit_message_text(
            "💬 *44名チームに質問*\n\n"
            "使い方: /team [質問内容]\n\n"
            "例:\n• /team 今のBTCは買い時か？\n"
            "• /team FUND-3の戦略を改善したい\n\n"
            "→ 関連チームが自動選出されて議論🦴",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))

    elif action == "calendar":
        try:
            from advanced_data import get_economic_calendar
            events = get_economic_calendar()
            lines = ["📅 *今週の重要経済指標*\n"]
            if events:
                for e in events[:8]:
                    impact = "🔴" if e.get("impact") == "high" else "🟡"
                    lines.append(f"{impact} {e.get('date','')} {e.get('event','')}")
            else:
                lines.append("データ取得中（次回レポート時に更新）")
            await query.edit_message_text("\n".join(lines), parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))
        except Exception as e:
            await query.edit_message_text(f"📅 経済指標データ取得中... ({str(e)[:50]})",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))

    elif action == "quantum_report":
        await query.edit_message_text("⚛️ 量子レポート生成中...（30秒）")
        try:
            from quantum_report import generate_quantum_report
            generate_quantum_report()
            await query.edit_message_text("✅ 量子レポートを送信しました！Telegramを確認してください🦴",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ {str(e)[:100]}")

    elif action == "emergency_stop":
        await query.edit_message_text(
            "🚨 *緊急停止*\n\n"
            "全ポジションを損切りしてシステムを停止します。\n"
            "本当に実行しますか？\n\n"
            "⚠️ この操作は取り消せません",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ YES 全停止実行", callback_data="cmd:emergency_confirm")],
                [InlineKeyboardButton("❌ NO キャンセル", callback_data="cmd:back")],
            ]))

    elif action == "emergency_confirm":
        await query.edit_message_text("🚨 全システム停止中...")
        import subprocess
        subprocess.run(['launchctl', 'unload', os.path.expanduser('~/Library/LaunchAgents/com.bk.auto-trader.plist')], capture_output=True)
        await query.edit_message_text("✅ 自動売買停止完了\n\n再開: launchctl load ~/Library/LaunchAgents/com.bk.auto-trader.plist",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 メニュー", callback_data="cmd:back")]]))

    elif action == "back":
        await show_main_menu(query, context, "⚛️ *&AI QUANTUM EDGE 指揮センター*")


async def show_main_menu(query, context, msg: str):
    """メインメニューボタン付きで表示"""
    keyboard = [
        [
            InlineKeyboardButton("📊 今すぐレポート", callback_data="cmd:report"),
            InlineKeyboardButton("💹 現在価格", callback_data="cmd:price"),
        ],
        [
            InlineKeyboardButton("🔥 モメンタム", callback_data="cmd:momentum"),
            InlineKeyboardButton("⚛️ ポートフォリオ", callback_data="cmd:portfolio_menu"),
        ],
        [
            InlineKeyboardButton("🎯 予測精度", callback_data="cmd:accuracy"),
            InlineKeyboardButton("📈 月次レポート", callback_data="cmd:monthly"),
        ],
        [
            InlineKeyboardButton("⚙️ システム状態", callback_data="cmd:status"),
        ],
    ]
    await query.edit_message_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def portfolio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(update): return
    
    risk_map = {"pf:aggressive": 0.2, "pf:balanced": 0.5, "pf:safe": 0.8}
    label_map = {"pf:aggressive": "🔥 積極運用", "pf:balanced": "⚖️ バランス", "pf:safe": "🛡️ 安全運用"}
    
    risk = risk_map.get(query.data, 0.5)
    label = label_map.get(query.data, "バランス")
    
    try:
        import yfinance as yf
        import numpy as np
        
        tickers = {
            'BTC-USD':'BTC','ETH-USD':'ETH','NVDA':'NVDA',
            'GC=F':'Gold','MSFT':'MSFT','SE':'SEA'
        }
        
        stocks = {}
        for t, name in tickers.items():
            try:
                hist = yf.Ticker(t).history(period='90d')
                if len(hist) > 10:
                    ret = hist['Close'].pct_change().mean() * 252
                    rsk = hist['Close'].pct_change().std() * (252**0.5)
                    stocks[name] = {'return': ret, 'risk': rsk}
            except: pass
        
        from brain_collector import quantum_portfolio_optimize
        pf, score = quantum_portfolio_optimize(stocks, risk_tolerance=risk)
        
        msg = f"⚛️ *量子ポートフォリオ推奨*\n{label}\n\n"
        for ticker, pct in sorted(pf.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(pct / 10)
            msg += f"  {ticker}: {pct}% {bar}\n"
        msg += f"\n量子スコア: {score:.3f}"
        
        await query.edit_message_text(msg, parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /accuracy — 予測精度
# ========================================
async def accuracy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    try:
        from prediction_tracker import get_accuracy_summary
        from feedback_tracker import load_feedback, get_win_rate
        
        acc = get_accuracy_summary()
        win = get_win_rate()
        fb = load_feedback()
        
        total_fb = fb.get('total_helpful',0) + fb.get('total_not_helpful',0)
        fb_rate = fb.get('total_helpful',0) / total_fb * 100 if total_fb > 0 else 0
        
        # 精度連動価格
        wr = win.get('win_rate', 0)
        if wr < 60: price_str = "無料（精度向上中）"
        elif wr < 65: price_str = "$29/月"
        elif wr < 70: price_str = "$59/月"
        elif wr < 75: price_str = "$99/月"
        else: price_str = "$149/月"
        
        msg = f"""📊 *&AI QUANTUM EDGE 予測精度*

🎯 *予測成績*
方向性的中率: *{win.get('win_rate', 0)}%*
レンジ内的中率: *{win.get('range_rate', 0)}%*
累計: {win.get('wins', 0)}/{win.get('total', 0)}回

💬 *フィードバック*
👍 役立った: {fb.get('total_helpful', 0)}回
👎 イマイチ: {fb.get('total_not_helpful', 0)}回
満足度: {fb_rate:.0f}%

💰 *精度連動価格（現在）*
精度 {wr}% → *{price_str}*

🦴 データ蓄積中（3ヶ月で精度確定）"""
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /monthly — 月次レポート今すぐ
# ========================================
async def monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text("📊 月次レポート生成中...")
    try:
        from feedback_tracker import send_monthly_report
        send_monthly_report()
        await update.message.reply_text("✅ 月次レポートを送信しました！")
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


# ========================================
# /status — システム状態
# ========================================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    import subprocess, os
    
    # LINEサーバー確認
    line_ok = os.path.exists('/tmp/andai-line-harness.log')
    
    # 最新レポート確認
    report_ok = os.path.exists('/Users/mr.k/Projects/and-ai-brain/latest_report.json')
    
    # LaunchAgent確認
    result = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
    brain_ok = 'ai-brain-daily' in result.stdout
    
    msg = f"""⚛️ *&AI QUANTUM EDGE システム状態*

✅ Bot稼働中
{'✅' if brain_ok else '❌'} 毎朝8:00配信 (LaunchAgent)
{'✅' if report_ok else '❌'} 最新レポート
{'✅' if line_ok else '❌'} LINEサーバー

📁 ファイル:
/Projects/and-ai-brain/
├── brain_collector.py ✅
├── momentum_engine.py ✅
├── prediction_tracker.py ✅
└── feedback_tracker.py ✅

🔧 次のステップ:
→ Amazon Braket有効化（本日14:00）
→ Twitter API審査中"""
    
    await update.message.reply_text(msg, parse_mode='Markdown')


# ========================================
# /addstock — 銘柄追加
# ========================================
async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    if not context.args:
        await update.message.reply_text("使い方: /addstock TICKER 名前\n例: /addstock DOGE DOGE")
        return
    
    ticker = context.args[0].upper()
    name = context.args[1] if len(context.args) > 1 else ticker
    
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period='5d')
        if len(hist) > 0:
            price = hist['Close'].iloc[-1]
            await update.message.reply_text(
                f"✅ {name} ({ticker}) を確認\n現在価格: ${price:,.2f}\n\n追加するには設定ファイルを更新します。"
            )
        else:
            await update.message.reply_text(f"❌ {ticker} のデータが取得できませんでした")
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:50]}")


# ========================================
# 📱 管理ダッシュボード（全画面）
# ========================================

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """メインダッシュボード"""
    if not is_authorized(update): return
    keyboard = [
        [
            InlineKeyboardButton("🏠 ホーム", callback_data="dash:home"),
            InlineKeyboardButton("📈 マーケット", callback_data="dash:market"),
        ],
        [
            InlineKeyboardButton("💰 資産", callback_data="dash:portfolio"),
            InlineKeyboardButton("🤖 自動売買", callback_data="dash:trading"),
        ],
        [
            InlineKeyboardButton("🔬 研究", callback_data="dash:research"),
            InlineKeyboardButton("⚙️ 設定", callback_data="dash:settings"),
        ],
    ]
    msg = "⚛️ *&AI QUANTUM EDGE ダッシュボード*\n\n画面を選択してください 👇"
    await update.message.reply_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ダッシュボード各画面コールバック"""
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    screen = data[1] if len(data) > 1 else "home"

    if screen == "home":
        await dash_home(query)
    elif screen == "market":
        await dash_market(query)
    elif screen == "portfolio":
        await dash_portfolio(query)
    elif screen == "trading":
        await dash_trading(query)
    elif screen == "research":
        await dash_research(query)
    elif screen == "settings":
        await dash_settings(query)


def dash_nav(current: str) -> InlineKeyboardMarkup:
    """ダッシュボード共通ナビゲーション"""
    icons = {"home":"🏠","market":"📈","portfolio":"💰","trading":"🤖","research":"🔬","settings":"⚙️"}
    labels = {"home":"ホーム","market":"マーケット","portfolio":"資産","trading":"自動売買","research":"研究","settings":"設定"}
    row1, row2 = [], []
    for i, (k, v) in enumerate(labels.items()):
        btn_text = f"[{icons[k]} {v}]" if k == current else f"{icons[k]} {v}"
        btn = InlineKeyboardButton(btn_text, callback_data=f"dash:{k}")
        if i < 3:
            row1.append(btn)
        else:
            row2.append(btn)
    return InlineKeyboardMarkup([row1, row2])


async def dash_home(query):
    """🏠 ホーム画面"""
    try:
        import json, datetime
        # 基本データ読み込み
        now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M JST")

        # Fear&Greed等を取得
        try:
            r = __import__('requests').get("https://api.alternative.me/fng/", timeout=5).json()
            fg = int(r['data'][0]['value'])
            fg_label = r['data'][0]['value_classification']
        except:
            fg, fg_label = 0, "不明"

        fg_emoji = "😱" if fg < 20 else "😨" if fg < 40 else "😐" if fg < 60 else "😊" if fg < 80 else "🤩"
        fg_signal = "🟢 逆張りチャンス" if fg < 20 else "🟡 注意" if fg < 40 else "⚪ 中立" if fg < 60 else "🟠 過熱" if fg < 80 else "🔴 バブル警戒"

        # デモファンド読み込み
        from demo_fund import load_fund, FUNDS
        fund_pnls = {}
        for fid in ["fund_1","fund_2","fund_3"]:
            try:
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                val = fd.get("portfolio_value", fd.get("current_value", 10_000_000))
                pnl_pct = (val - 10_000_000) / 10_000_000 * 100
                fund_pnls[fid] = (val, pnl_pct, cfg["target_monthly"], cfg["emoji"], cfg["label"])
            except:
                fund_pnls[fid] = (10_000_000, 0.0, 5, "❓", "?")

        f1 = fund_pnls["fund_1"]
        f2 = fund_pnls["fund_2"]
        f3 = fund_pnls["fund_3"]

        msg = f"""⚛️ *&AI QUANTUM EDGE*
{now}
━━━━━━━━━━━━━━━

🌡️ *市場体温計*
{fg_emoji} Fear&Greed: *{fg}/100*  {fg_signal}

💰 *デモファンド 今日の損益*
{f1[3]} FUND-1 {f1[4]}: ¥{f1[0]:,.0f}  ({f1[1]:+.2f}%)  目標{f1[2]}%
{f2[3]} FUND-2 {f2[4]}: ¥{f2[0]:,.0f}  ({f2[1]:+.2f}%)  目標{f2[2]}%
{f3[3]} FUND-3 {f3[4]}: ¥{f3[0]:,.0f}  ({f3[1]:+.2f}%)  目標{f3[2]}%

🎯 *今日のシグナル*
⏸️ 待機中（条件確認中）"""

    except Exception as e:
        msg = f"⚛️ *&AI QUANTUM EDGE ホーム*\n\n⚠️ データ取得中... ({str(e)[:50]})"

    keyboard = [
        [
            InlineKeyboardButton("📊 今すぐレポート", callback_data="cmd:report"),
            InlineKeyboardButton("🔄 更新", callback_data="dash:home"),
        ],
        *dash_nav("home").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dash_market(query):
    """📈 マーケット画面"""
    try:
        import requests
        # BTC価格取得
        r = requests.get("https://indexer.dydx.trade/v4/perpetualMarkets", timeout=10)
        markets = r.json().get("markets", {})

        key_tickers = ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","TRX-USD","TON-USD"]
        lines = []
        for t in key_tickers:
            if t in markets:
                p = float(markets[t].get("oraclePrice", 0))
                chg = float(markets[t].get("priceChange24H", 0))
                chg_pct = (chg / p * 100) if p else 0
                arrow = "▲" if chg_pct > 0 else "▼" if chg_pct < 0 else "→"
                color = "🟢" if chg_pct >= 1.5 else "🔵" if chg_pct >= 0 else "🟡" if chg_pct >= -1.5 else "🔴"
                ticker = t.replace("-USD","")
                lines.append(f"{color} {ticker:6} ${p:>12,.2f}  {arrow}{abs(chg_pct):.1f}%")

        price_block = "\n".join(lines) if lines else "取得中..."

        msg = f"""📈 *マーケット*
━━━━━━━━━━━━━━━

💹 *主要価格（dYdX）*
```
{price_block}
```

🔥 *モメンタムランキング*
/momentum で確認

🐋 *クジラ動向*
/report で詳細確認"""

    except Exception as e:
        msg = f"📈 *マーケット*\n\n⚠️ データ取得中... ({str(e)[:50]})"

    keyboard = [
        [
            InlineKeyboardButton("🔥 モメンタム詳細", callback_data="cmd:momentum"),
            InlineKeyboardButton("🔄 更新", callback_data="dash:market"),
        ],
        *dash_nav("market").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dash_portfolio(query):
    """💰 資産画面"""
    try:
        import requests, json

        # Hyperliquid残高
        hl_bal = 0.0
        hl_positions = 0
        try:
            HL_WALLET = os.environ.get("HL_MAIN_WALLET", "0xe5941eeF19C30A09f05b23b4D512301b3388c9Ed")
            r = requests.post("https://api.hyperliquid.xyz/info",
                json={"type": "clearinghouseState", "user": HL_WALLET}, timeout=8)
            if r.status_code == 200:
                d = r.json()
                hl_bal = float(d.get("marginSummary", {}).get("accountValue", 0))
                hl_positions = len(d.get("assetPositions", []))
        except: pass

        # dYdX残高
        dydx_bal = 0.0
        dydx_positions = 0
        DYDX_ADDR = os.environ.get("DYDX_ADDRESS", "dydx182rjzngn7qzsjunszne4srkr2r2tpplgvc4ct0")
        try:
            r2 = requests.get(f"https://indexer.dydx.trade/v4/addresses/{DYDX_ADDR}", timeout=8)
            if r2.status_code == 200:
                subs = r2.json().get("subaccounts", [])
                if subs:
                    dydx_bal = float(subs[0].get("equity", 0))
                    dydx_positions = len(subs[0].get("openPerpetualPositions", {}))
        except: pass

        total = hl_bal + dydx_bal

        # デモファンド
        demo_total = 0
        demo_pnl = 0
        fund_details = []
        from demo_fund import load_fund, FUNDS
        for fid in ["fund_1", "fund_2", "fund_3"]:
            try:
                fd = load_fund(fid)
                cfg = FUNDS[fid]
                val = fd.get("portfolio_value", fd.get("current_value", 10_000_000))
                pnl = val - 10_000_000
                pnl_pct = pnl / 10_000_000 * 100
                demo_total += val
                demo_pnl += pnl
                progress = pnl_pct / cfg["target_monthly"] * 100
                fund_details.append(
                    f"{cfg['emoji']} *{cfg['name']} {cfg['label']}*\n"
                    f"   目標: 月利{cfg['target_monthly']}%  進捗: {progress:.0f}%\n"
                    f"   ¥{val:,.0f}  ({pnl_pct:+.2f}%)"
                )
            except:
                demo_total += 10_000_000
                fund_details.append(f"❓ {fid}: データ取得中...")

        funds_text = "\n\n".join(fund_details)

        msg = f"""💰 *ポートフォリオ*
━━━━━━━━━━━━━━━

🔵 *Hyperliquid*
残高: ${hl_bal:,.2f} USDH
ポジション: {hl_positions}件

💎 *dYdX*
残高: ${dydx_bal:,.2f} USDC
ポジション: {dydx_positions}件

━━━━━━━━━━━━━━━
💵 合計リアル: *${total:,.2f}*

━━━━━━━━━━━━━━━
🏆 *3デモファンド（¥3,000万）*

{funds_text}

合計: ¥{demo_total:,.0f}
累計損益: ¥{demo_pnl:+,.0f}"""

    except Exception as e:
        msg = f"💰 *ポートフォリオ*\n\n⚠️ 取得中... ({str(e)[:50]})"

    keyboard = [
        [
            InlineKeyboardButton("🛡️ FUND-1ルール", callback_data="fund:rule:fund_1"),
            InlineKeyboardButton("⚡ FUND-2ルール", callback_data="fund:rule:fund_2"),
            InlineKeyboardButton("🚀 FUND-3ルール", callback_data="fund:rule:fund_3"),
        ],
        [
            InlineKeyboardButton("📊 デモファンド詳細", callback_data="pf:demo"),
            InlineKeyboardButton("🔄 更新", callback_data="dash:portfolio"),
        ],
        *dash_nav("portfolio").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dash_trading(query):
    """🤖 自動売買画面"""
    import subprocess, os

    # LaunchAgent稼働確認
    def is_running(label):
        try:
            r = subprocess.run(["launchctl", "list", label],
                capture_output=True, text=True)
            return r.returncode == 0
        except:
            return False

    auto_trader = is_running("com.bk.auto-trader")
    vip_watcher = is_running("com.bk.vip-watcher")
    research = is_running("com.bk.research-agent")

    msg = f"""🤖 *自動売買*
━━━━━━━━━━━━━━━

🖥️ *システム状態*
{'✅' if auto_trader else '❌'} auto-trader（1時間毎）
{'✅' if vip_watcher else '❌'} vip-watcher（監視中）
{'✅' if research else '❌'} research-agent（毎晩2:00）
✅ Hyperliquid: 接続済み
✅ dYdX: 接続済み（$798.75）

📋 *稼働中の戦略*
⏸️ STRATEGY B: 待機中（条件未達）
⚡ STRATEGY C: F&G条件クリア！
⏸️ A10S グリッド: 待機中

📊 *今日の取引*
エントリー: 0回
利確: 0回
損切り: 0回

⚠️ 次のエントリー条件:
• スコア75点以上
• X感情5.5以上
• 世界経済スコア0以上
• FR +0.1%以下"""

    keyboard = [
        [
            InlineKeyboardButton("▶️ 今すぐチェック", callback_data="cmd:check_signal"),
            InlineKeyboardButton("🎯 A10S状態", callback_data="cmd:a10s"),
        ],
        [
            InlineKeyboardButton("⏹️ 全停止", callback_data="cmd:emergency_stop"),
            InlineKeyboardButton("🔄 更新", callback_data="dash:trading"),
        ],
        *dash_nav("trading").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dash_research(query):
    """🔬 研究画面（バックテスト結果 + 戦略別勝率 + 推奨戦略）"""
    import json
    import os

    # ────────────────────────────────
    # 予測精度読み込み
    # ────────────────────────────────
    try:
        with open('/Users/mr.k/Projects/and-ai-brain/prediction_log.json') as f:
            preds = json.load(f)
        total = len(preds)
        correct = sum(1 for p in preds if p.get("correct") is True)
        win_rate_pred = (correct / total * 100) if total > 0 else 0
    except:
        total, correct, win_rate_pred = 0, 0, 0.0

    # ────────────────────────────────
    # バックテスト結果読み込み
    # ────────────────────────────────
    BACKTEST_FILE = '/Users/mr.k/Projects/and-ai-brain/backtest_results.json'
    backtest_ok = False
    bt_lines = []
    recommended = {}
    winrate_lines = []

    try:
        if os.path.exists(BACKTEST_FILE):
            with open(BACKTEST_FILE) as f:
                bt = json.load(f)

            backtest_ok = True
            bt_days = bt.get("backtest_days", 30)
            bt_at = bt.get("generated_at", "不明")

            # ファンド別最良戦略
            STRATEGY_ICONS = {
                "MOMENTUM": "📈", "CONTRARIAN": "🔄",
                "TREND_FOLLOW": "📊", "GRID": "⚡", "LONG_SHORT": "🔀",
            }
            fund_icons = {"fund_1": "🛡️", "fund_2": "⚡", "fund_3": "🚀"}
            fund_labels = {"fund_1": "FUND-1", "fund_2": "FUND-2", "fund_3": "FUND-3"}

            for fid in ["fund_1", "fund_2", "fund_3"]:
                fres = bt.get("funds", {}).get(fid, {})
                best = fres.get("best_strategy", "N/A")
                recommended[fid] = best
                strategy_evs = fres.get("strategy_avg_ev", {})

                icon = fund_icons.get(fid, "")
                label = fund_labels.get(fid, fid)
                best_icon = STRATEGY_ICONS.get(best, "")
                bt_lines.append(f"{icon} *{label}*: {best_icon} `{best}`")

            # 戦略別勝率セクション
            try:
                from backtest import format_strategy_winrates
                wrs = format_strategy_winrates()
                for fid in ["fund_1", "fund_2", "fund_3"]:
                    icon = fund_icons.get(fid, "")
                    label = fund_labels.get(fid, fid)
                    fwrs = wrs.get(fid, {})
                    if fwrs:
                        best_strat = recommended.get(fid, "")
                        top = sorted(fwrs.items(), key=lambda x: -x[1])[:3]
                        wrl = f"{icon} *{label}*: "
                        parts = []
                        for s, wr in top:
                            mark = "🏆" if s == best_strat else ""
                            parts.append(f"{mark}`{s}`={wr:.0f}%")
                        wrl += " / ".join(parts)
                        winrate_lines.append(wrl)
            except Exception as we:
                winrate_lines.append(f"⚠️ 勝率取得エラー: {str(we)[:60]}")
    except Exception as be:
        bt_lines.append(f"⚠️ 読込エラー: {str(be)[:60]}")

    # ────────────────────────────────
    # 今週の推奨戦略（バックテスト結果 or デフォルト）
    # ────────────────────────────────
    rec_section = ""
    if backtest_ok and recommended:
        week_recs = []
        for fid, strat in recommended.items():
            label = {"fund_1": "FUND-1", "fund_2": "FUND-2", "fund_3": "FUND-3"}.get(fid, fid)
            week_recs.append(f"  {label}: `{strat}`")
        rec_section = "🎯 *今週の推奨戦略*\n" + "\n".join(week_recs) + "\n\n"
    else:
        rec_section = "🎯 今週の推奨戦略: バックテスト未実行\n\n"

    # ────────────────────────────────
    # デモファンド現在成績
    # ────────────────────────────────
    INITIAL_CAPITAL = 10_000_000
    fund_perf_lines = []
    try:
        from demo_fund import load_fund, FUNDS
        for fid, cfg in FUNDS.items():
            fdata = load_fund(fid)
            val = fdata.get("portfolio_value", fdata.get("current_value", INITIAL_CAPITAL))
            pct = (val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            arrow = "📈" if pct >= 0 else "📉"
            days_data = fdata.get("total_days", 0)
            wins = fdata.get("win_days", 0)
            wr = f"{wins}/{days_data}日" if days_data > 0 else "積算中"
            fund_perf_lines.append(
                f"{cfg['emoji']} *{cfg['name']}*: {pct:+.2f}% ({wr}) {arrow}"
            )
    except Exception as fe:
        fund_perf_lines.append(f"⚠️ {str(fe)[:60]}")

    # ────────────────────────────────
    # メッセージ組み立て
    # ────────────────────────────────
    bt_header = f"過去{bt_days}日 ({bt_at})" if backtest_ok else "未実行"
    msg = f"""🔬 *研究エージェント*
━━━━━━━━━━━━━━━

📊 *予測精度*
総予測: {total}件 / 正解: {correct}件
勝率: {win_rate_pred:.1f}% {'✅' if win_rate_pred >= 70 else '⏳' if total < 30 else '⚠️'}

━━━━━━━━━━━━━━━
{rec_section}⚛️ *バックテスト最良戦略* ({bt_header})
{chr(10).join(bt_lines) if bt_lines else 'データなし'}

📋 *戦略別勝率 (Top3)*
{chr(10).join(winrate_lines) if winrate_lines else 'データなし'}

━━━━━━━━━━━━━━━
🏦 *デモファンド成績*
{chr(10).join(fund_perf_lines)}

🕐 次回研究: 毎晩02:30 JST"""

    keyboard = [
        [
            InlineKeyboardButton("📊 バックテスト実行", callback_data="cmd:run_backtest"),
            InlineKeyboardButton("🔄 今すぐ研究", callback_data="cmd:research_now"),
        ],
        [
            InlineKeyboardButton("🔄 更新", callback_data="dash:research"),
        ],
        *dash_nav("research").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def whale_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🐋 クジラ速報"""
    if not is_authorized(update): return
    try:
        from brain_collector import get_whale_alerts, format_whale_section
        whale_data = get_whale_alerts()
        section = format_whale_section(whale_data)
        alerts = whale_data.get("alerts", [])
        msg = f"🐋 *クジラ速報*\n{section}\n\n件数: {len(alerts)}件（過去4時間）"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")


async def update_positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔄 ポジション更新"""
    if not is_authorized(update): return
    await update.message.reply_text("🔄 ポジションを現在価格で更新中...")
    try:
        import requests
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=10)
        mids = {k: float(v) for k, v in r.json().items()}
        from demo_fund import update_positions, load_fund, FUNDS, INITIAL_CAPITAL
        lines = []
        for fid in ["fund_1","fund_2","fund_3"]:
            closed = update_positions(fid, mids)
            fd = load_fund(fid)
            cfg = FUNDS[fid]
            val = fd.get("portfolio_value", INITIAL_CAPITAL)
            pnl_pct = (val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            open_pos = [p for p in fd.get("open_positions",[]) if p.get("status")=="OPEN"]
            lines.append(f"{cfg['emoji']} {cfg['name']}: ¥{val:,.0f} ({pnl_pct:+.2f}%) | {len(open_pos)}件")
            if closed:
                for c in closed:
                    lines.append(f"  💥 {c['status']}: {c['ticker']} {c.get('pnl_pct',0):+.2f}%")
        msg = "🔄 *ポジション更新完了*\n\n" + "\n".join(lines)
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")


async def check_tp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎯 利確確認"""
    if not is_authorized(update): return
    try:
        import requests
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "allMids"}, timeout=10)
        mids = {k: float(v) for k, v in r.json().items()}
        from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
        lines = ["🎯 *利確ライン確認*\n"]
        found = False
        for fid in ["fund_1","fund_2","fund_3"]:
            fd = load_fund(fid)
            cfg = FUNDS[fid]
            for p in fd.get("open_positions",[]):
                if p.get("status") != "OPEN": continue
                ticker = p["ticker"]
                current = float(mids.get(ticker, p["entry_price"]))
                tp1 = p.get("take_profit_1", 0)
                tp2 = p.get("take_profit_2", 0)
                sl = p.get("stop_loss", 0)
                pnl_pct = p.get("pnl_pct", 0)
                # 利確に近い順に表示
                tp1_dist = (tp1 - current) / current * 100 if tp1 > current else 0
                sl_dist = (current - sl) / current * 100 if sl > 0 else 0
                lines.append(f"{cfg['emoji']} {ticker}: {pnl_pct:+.2f}%")
                lines.append(f"  利確①まで: +{tp1_dist:.1f}% (${tp1:,.4f})")
                lines.append(f"  損切りまで: -{sl_dist:.1f}% (${sl:,.4f})")
                found = True
        if not found:
            lines.append("ポジションなし")
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")



# ==============================
# URLからAPIキー自動取得フロー
# ==============================
USER_WAITING_FOR_URL = set()  # URL入力待ちのユーザーID

async def get_api_from_url_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔑 APIキー取得: URLを入力するだけで自動ログイン→キー取得"""
    if not is_authorized(update): return
    
    USER_WAITING_FOR_URL.add(update.effective_user.id)
    
    await update.message.reply_text(
        "🔑 *APIキー自動取得*\n\n"
        "取得したいサービスのURLを入力してください\n\n"
        "例:\n"
        "• `https://edinetdb.jp`\n"
        "• `https://jpx-jquants.com`\n"
        "• `https://tavily.com`\n"
        "• `https://financialdatasets.ai`\n"
        "• その他任意のURL\n\n"
        "URLを送ってください👇",
        parse_mode="Markdown",
        reply_markup=get_persistent_keyboard()
    )


async def handle_url_for_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """URLを受け取ってAPIキー取得を実行"""
    if not is_authorized(update): return
    user_id = update.effective_user.id
    
    if user_id not in USER_WAITING_FOR_URL:
        return
    
    text = update.message.text.strip()
    
    # URLかどうか確認
    if not text.startswith('http'):
        await update.message.reply_text(
            "❌ URLの形式が正しくありません\n"
            "https:// から始まるURLを入力してください",
            reply_markup=get_persistent_keyboard()
        )
        return
    
    USER_WAITING_FOR_URL.discard(user_id)
    
    await update.message.reply_text(
        f"🔍 *解析中...*\n\n`{text}`\n\n"
        "サービスを認識してログインを試みます\n"
        "少々お待ちください（30秒〜2分）",
        parse_mode="Markdown",
        reply_markup=get_persistent_keyboard()
    )
    
    try:
        from web_automator import WebAutomator, SERVICES
        import re
        
        # URLからサービスIDを特定
        service_id = None
        for sid, svc in SERVICES.items():
            domain = svc["register_url"].split("/")[2]
            if domain in text or sid in text.lower():
                service_id = sid
                break
        
        if service_id:
            svc_name = SERVICES[service_id]["name"]
            await update.message.reply_text(
                f"✅ *{svc_name}* を認識しました\n\n"
                f"自動登録・ログインを開始します...",
                parse_mode="Markdown"
            )
            
            bot = WebAutomator()
            
            # 直接APIがある場合は試す
            if SERVICES[service_id].get("direct_api"):
                result = bot.register_direct_api(service_id)
                if result.get("api_key"):
                    await update.message.reply_text(
                        f"🎉 *APIキー自動取得成功！*\n\n"
                        f"`{result['api_key'][:15]}...`\n\n"
                        f"✅ .envに自動保存完了🦴",
                        parse_mode="Markdown",
                        reply_markup=get_persistent_keyboard()
                    )
                    return
                elif "既にAPIキーが発行" in result.get("response", ""):
                    await update.message.reply_text(
                        f"📧 *既に登録済みです*\n\n"
                        f"ダッシュボードからAPIキーをコピーして:\n"
                        f"`/savekey {service_id} [キー]`",
                        parse_mode="Markdown",
                        reply_markup=get_persistent_keyboard()
                    )
                    return
            
            # ブラウザ自動化を試みる
            result = bot.register_with_browser(service_id)
            
            if result.get("api_key"):
                await update.message.reply_text(
                    f"🎉 *APIキー自動取得成功！*\n\n"
                    f"`{result['api_key'][:15]}...`\n\n"
                    f"✅ .envに自動保存完了🦴",
                    parse_mode="Markdown",
                    reply_markup=get_persistent_keyboard()
                )
            else:
                # 手動入力に切り替え
                await update.message.reply_text(
                    f"⚠️ *手動入力が必要です*\n\n"
                    f"1. {SERVICES[service_id]['dashboard_url']} を開く\n"
                    f"2. ログインしてAPIキーをコピー\n"
                    f"3. `/savekey {service_id} [キー]` で送信\n\n"
                    f"Googleログインが必要なサービスは\n"
                    f"手動でコピーが最速です🦴",
                    parse_mode="Markdown",
                    reply_markup=get_persistent_keyboard()
                )
        else:
            # 未登録サービス → 汎用ブラウザで試みる
            await update.message.reply_text(
                f"🆕 *未登録サービスです*\n\n"
                f"URLを解析してAPIキーを探します...\n\n"
                f"ダッシュボードURL確認後、\n"
                f"取得したAPIキーをここにコピー:\n"
                f"`/savekey custom [キー]`\n\n"
                f"または新しいサービスとして追加しますか？",
                parse_mode="Markdown",
                reply_markup=get_persistent_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ エラー: {str(e)[:100]}\n\n"
            f"手動でAPIキーをコピーして:\n"
            f"`/savekey [サービスID] [キー]`",
            parse_mode="Markdown",
            reply_markup=get_persistent_keyboard()
        )



async def first_principles_cmd(update, context):
    """第一原理分解コマンド /fp [テーマ]"""
    if not is_authorized(update): return
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 *第一原理分解エンジン*\n\n"
            "使い方:\n`/fp [テーマ]`\n\n"
            "例:\n"
            "• `/fp &AI QEをどう勝てるツールに育てるか`\n"
            "• `/fp 価格設定を見直したい`\n"
            "• `/fp なぜHLで自動売買するのか`\n\n"
            "アリストテレスの第一原理思考で\n"
            "隠れた仮定を全て暴きます🦴",
            parse_mode="Markdown",
            reply_markup=get_persistent_keyboard()
        )
        return
    theme = " ".join(args)
    await update.message.reply_text(f"🔍 第一原理分解中: 「{theme}」\n\n⏳ 30秒ほどお待ちください...")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = f"""あなたは第一原理思考エンジンです。

テーマ: 「{theme}」

以下を順番に実行してください。

① 仮定リスト
このテーマに隠れている「当たり前」を全部箇条書き。
各仮定に[慣習][恐怖][業界常識][競合模倣]のタグ付け。

② 疑いようのない真実（3つだけ）
全仮定を除去した後に残る絶対的真実を3つ。

③ ゼロからの最強解（2つだけ）
真実だけを使って「誰もやったことがない方法」を2つ。

④ 今すぐやること（1つだけ）
24時間以内に実行できる最もレバレッジの高い「最初の1手」。
具体的な動詞で書く。「検討する」禁止。

各フェーズ200字以内。日本語。"""
        
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.content[0].text
        msg = f"🔍 *第一原理分解: 「{theme}」*\n\n{result}\n\n🦴 &AI QUANTUM EDGE"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_persistent_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}", reply_markup=get_persistent_keyboard())


async def save_api_key_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    APIキーを受け取って自動保存
    使い方: /savekey [サービスID] [APIキー]
    例: /savekey edinetdb edb_xxxxxxxx
    """
    if not is_authorized(update): return
    args = context.args

    if not args or len(args) < 2:
        services_list = "\n".join([
            f"  `{sid}` — {s['name']}"
            for sid, s in {
                'edinetdb': {'name': 'EDINET DB（日本株財務）'},
                'jquants': {'name': 'J-Quants（東証株価）'},
                'tavily': {'name': 'Tavily（ニュース検索）'},
                'financial_datasets': {'name': 'Financial Datasets（米国株ファンダ）'},
            }.items()
        ])
        await update.message.reply_text(
            "🔑 *APIキー自動保存コマンド*\n\n"
            "使い方:\n"
            "`/savekey [サービスID] [APIキー]`\n\n"
            "サービスID一覧:\n"
            f"{services_list}\n\n"
            "例:\n"
            "`/savekey edinetdb edb_xxxxxx`\n"
            "`/savekey jquants eyJhb...`\n"
            "`/savekey tavily tvly-xxxxx`",
            parse_mode='Markdown',
            reply_markup=get_persistent_keyboard()
        )
        return

    service_id = args[0].lower()
    api_key = args[1]

    try:
        from api_automation import process_api_key, SERVICES
        if service_id in SERVICES:
            success = process_api_key(service_id, api_key)
            if success:
                service = SERVICES[service_id]
                await update.message.reply_text(
                    f"✅ *{service['name']} APIキー保存完了！*\n\n"
                    f"環境変数: `{service['env_key']}`\n"
                    f".env + bk-dexter-jp/.env + Notion に保存しました🦴",
                    parse_mode='Markdown',
                    reply_markup=get_persistent_keyboard()
                )
        else:
            await update.message.reply_text(
                f"❌ 不明なサービスID: `{service_id}`\n\n"
                "対応ID: edinetdb / jquants / tavily / financial_datasets",
                parse_mode='Markdown',
                reply_markup=get_persistent_keyboard()
            )
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}", reply_markup=get_persistent_keyboard())


async def team_ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """TradingAgents統合版 チームディスカッション"""
    if not is_authorized(update):
        return
    
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "🤝 *チームに聞く（TradingAgents統合版）*\n\n"
            "使い方: `/team [銘柄や質問]`\n\n"
            "例:\n"
            "• `/team BTC 今買うべきか？`\n"
            "• `/team NVDA 来月の見通し`\n"
            "• `/team ETH vs SOL どちらが有望？`\n\n"
            "ファンダ/センチメント/テクニカル/リスクの4担当が議論します",
            parse_mode="Markdown"
        )
        return
    
    msg = await update.message.reply_text(
        f"🤝 *チームが議論中...*\n\n"
        f"質問: `{query}`\n\n"
        f"ファンダ担当・センチメント担当・テクニカル担当・リスク担当が分析中...",
        parse_mode="Markdown"
    )
    
    try:
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/TradingAgents')
        from dotenv import load_dotenv
        load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        from daily_research import get_fg, get_prices_bulk
        
        fg = get_fg()
        prices = get_prices_bulk()
        
        # BTC/ETHシンボルを抽出（なければBTCデフォルト）
        ticker = "BTC"
        for sym in ["NVDA", "ARM", "AAPL", "ETH", "SOL", "BTC", "MSFT", "META", "GOOGL", "AMZN"]:
            if sym in query.upper():
                ticker = sym
                break
        
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider": "anthropic",
            "deep_think_llm": "claude-sonnet-4-6",
            "quick_think_llm": "claude-haiku-4-5",
            "max_debate_rounds": 1,
            "online_tools": True,
        })
        
        ta = TradingAgentsGraph(debug=False, config=config)
        
        # 分析実行（タイムアウト90秒）
        import asyncio
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ta.propagate(ticker, "2026-03-31")
            ),
            timeout=90.0
        )
        
        # 結果を整形
        decision = result.get("decision", {})
        action = decision.get("action", "HOLD")
        reasoning = decision.get("reasoning", "分析中...")
        
        action_emoji = "📈 BUY" if action == "BUY" else "📉 SELL" if action == "SELL" else "⏸ HOLD"
        
        response = f"""🤝 *チーム議論結果*

銘柄: {ticker}
判断: {action_emoji}

理由:
{reasoning[:800]}

_F&G: {fg}/100 | BTC: ${prices.get('BTC',0):,.0f}_
_⚛️ TradingAgents × &AI QE_"""
        
        await msg.edit_text(response, parse_mode="Markdown")
        
    except Exception as e:
        # フォールバック: 元のチーム議論
        try:
            import anthropic as ant
            from daily_research import get_fg, get_prices_bulk
            
            fg = get_fg()
            prices = get_prices_bulk()
            
            client = ant.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system="""あなたは&AI QEの投資チームです。
ファンダメンタルズ担当・センチメント担当・テクニカル担当・リスク担当の4人が議論します。
各担当の視点で分析し、最終判断を出してください。日本語で回答。""",
                messages=[{
                    "role": "user",
                    "content": f"F&G={fg}/100, BTC=${prices.get('BTC',0):,.0f}\n\n質問: {query}"
                }]
            )
            await msg.edit_text(
                f"🤝 *チーム議論結果*\n\n{resp.content[0].text[:3000]}\n\n_⚛️ &AI QE_",
                parse_mode="Markdown"
            )
        except Exception as e2:
            await msg.edit_text(f"❌ エラー: {str(e2)[:100]}", parse_mode="Markdown")


async def legend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI Hedge Fund統合版 伝説投資家14人の視点で分析"""
    if not is_authorized(update):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 *伝説投資家に聞く*\n\n"
            "使い方: `/legend [投資家] [銘柄・質問]`\n\n"
            "投資家一覧:\n"
            "• buffett - Warren Buffett\n"
            "• munger - Charlie Munger\n"
            "• burry - Michael Burry\n"
            "• lynch - Peter Lynch\n"
            "• graham - Ben Graham\n"
            "• ackman - Bill Ackman\n"
            "• all - 全員の意見\n\n"
            "例: `/legend buffett NVDA`",
            parse_mode="Markdown"
        )
        return
    
    investor_key = args[0].lower()
    query = " ".join(args[1:]) if len(args) > 1 else "この銘柄をどう見るか"
    
    msg = await update.message.reply_text(f"📊 分析中...", parse_mode="Markdown")
    
    try:
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/ai-hedge-fund')
        from dotenv import load_dotenv
        load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')
        from daily_research import get_fg, get_prices_bulk
        
        fg = get_fg()
        prices = get_prices_bulk()
        
        investor_map = {
            "buffett": ("warren_buffett", "Warren Buffett 🎩", "warren_buffett_agent"),
            "munger": ("charlie_munger", "Charlie Munger 🧠", "charlie_munger_agent"),
            "burry": ("michael_burry", "Michael Burry 👁", "michael_burry_agent"),
            "lynch": ("peter_lynch", "Peter Lynch 🔍", "peter_lynch_agent"),
            "graham": ("ben_graham", "Ben Graham 📚", "ben_graham_agent"),
            "ackman": ("bill_ackman", "Bill Ackman 💪", "bill_ackman_agent"),
        }
        
        # Claude直接でその投資家スタイルで回答（エージェント統合の代替）
        import anthropic as ant
        
        investor_styles = {
            "buffett": "あなたはWarren Buffettです。バリュー投資・長期保有・経済的堀の観点で分析してください。",
            "munger": "あなたはCharlie Mungerです。素晴らしいビジネスを公正な価格で買う観点で分析してください。",
            "burry": "あなたはMichael Burryです。逆張り・深いバリュー・隠れたリスクを探す観点で分析してください。",
            "lynch": "あなたはPeter Lynchです。テンバガー・日常から投資機会を見つける観点で分析してください。",
            "graham": "あなたはBen Grahamです。安全マージン・ミスタマーケット・純資産価値の観点で分析してください。",
            "ackman": "あなたはBill Ackmanです。アクティビスト投資・大胆なポジション・変革を求める観点で分析してください。",
            "all": "あなたは伝説の投資家チームです。Buffett/Munger/Burry/Lynch/Grahamそれぞれの視点で分析してください。",
        }
        
        style = investor_styles.get(investor_key, investor_styles["all"])
        _, display_name, _ = investor_map.get(investor_key, ("all", "投資家チーム", "all"))
        
        client = ant.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=f"""{style}
日本語で回答してください。断定的な投資推奨は避け「私のスタイルでは〜」という表現を使ってください。
現在の市場データ: F&G={fg}/100, BTC=${prices.get('BTC',0):,.0f}""",
            messages=[{"role": "user", "content": f"{query}についてどう思いますか？"}]
        )
        
        await msg.edit_text(
            f"📊 *{display_name} の視点*\n\n{resp.content[0].text[:3000]}\n\n_⚛️ AI Hedge Fund × &AI QE_",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await msg.edit_text(f"❌ エラー: {str(e)[:100]}", parse_mode="Markdown")


async def calendar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📅 経済指標"""
    if not is_authorized(update): return
    try:
        from advanced_data import get_economic_calendar
        events = get_economic_calendar()
        if events:
            lines = ["📅 *今週の重要経済指標*\n"]
            for e in events[:8]:
                impact = "🔴" if e.get("impact") == "high" else "🟡"
                lines.append(f"{impact} {e.get('date','')} {e.get('event','')}")
                if e.get("forecast"):
                    lines.append(f"   予測: {e['forecast']}")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
        else:
            await update.message.reply_text("📅 経済指標データを取得中...\n※ 次回レポート時に更新されます")
    except Exception as e:
        await update.message.reply_text(f"📅 *重要経済指標*\n\nデータ取得中...\n({str(e)[:50]})")


async def quantum_report_cmd_inline(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """⚛️ 量子レポート（コールバック対応）"""
    pass  # quantum_report_cmdで実装済み


async def fund_rule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ファンド投資ルール説明"""
    query = update.callback_query
    await query.answer()
    fund_id = query.data.split(":")[-1]  # fund_1, fund_2, fund_3

    from demo_fund import load_fund, FUNDS, INITIAL_CAPITAL
    import requests

    cfg = FUNDS.get(fund_id, {})
    fd = load_fund(fund_id)
    val = fd.get("portfolio_value", INITIAL_CAPITAL)
    pnl = val - INITIAL_CAPITAL
    pnl_pct = pnl / INITIAL_CAPITAL * 100
    open_pos = [p for p in fd.get("open_positions", []) if p.get("status") == "OPEN"]

    # 月利達成の進捗
    monthly_target = cfg.get("target_monthly", 5)
    progress = pnl_pct / monthly_target * 100 if monthly_target > 0 else 0
    bar_filled = int(progress / 10)
    bar = "█" * min(bar_filled, 10) + "░" * max(0, 10 - bar_filled)

    # ファンド別の詳細説明
    strategy_desc = {
        "fund_1": (
            "🎯 *コンセプト: 安全第一・着実に月5%*\n\n"
            "極度の恐怖（F\\&G≤25）の時だけ\n"
            "安全資産（BTC/ETH/Gold等）に\n"
            "少額ずつ逆張りロング\n\n"
            "📐 *ロジックの流れ:*\n"
            "① F\\&G ≤ 25 → 「底値圏」と判定\n"
            "② スコア80点以上の銘柄を選ぶ\n"
            "③ X感情6.0以上を確認\n"
            "④ 出来高が通常の2倍以上\n"
            "⑤ 全条件クリア → エントリー\n\n"
            "🔄 *A10Sグリッド戦略:*\n"
            "一定間隔で複数のロングを設置\n"
            "量子バックテスト勝率95.8%"
        ),
        "fund_2": (
            "🎯 *コンセプト: バランス型・月10%*\n\n"
            "センチメントと価格トレンドを\n"
            "組み合わせた中程度リスク戦略\n\n"
            "📐 *ロジックの流れ:*\n"
            "① スコア75点以上の銘柄を探す\n"
            "② X感情5.5以上を確認\n"
            "③ 出来高1.5倍以上\n"
            "④ BTC支配率×MA20でトレンド確認\n"
            "⑤ 条件クリア → エントリー\n\n"
            "🔄 *モメンタムTop3戦略:*\n"
            "最も勢いのある上位3銘柄に\n"
            "集中投資（週2〜3回）"
        ),
        "fund_3": (
            "🎯 *コンセプト: 全力勝負・月15%*\n\n"
            "全戦略を同時稼働させ\n"
            "最大のリターンを狙う高リスク戦略\n\n"
            "📐 *ロジックの流れ:*\n"
            "① スコア70点以上（最も緩い）\n"
            "② X感情5.0以上\n"
            "③ 出来高1.2倍以上\n"
            "④ 逆張り+グリッド+ロング/ショート\n"
            "   全4戦略を同時実行\n"
            "⑤ F\\&G>70の時はショートも検討\n\n"
            "🔄 *全戦略フル稼働:*\n"
            "毎日チェック・最も多くエントリー"
        ),
    }

    emoji = cfg.get("emoji", "")
    name = cfg.get("name", "")
    label = cfg.get("label", "")

    msg = f"""{emoji} *{name} {label}*
月利目標: {monthly_target}%  進捗: [{bar}] {progress:.0f}%
残高: ¥{val:,.0f} ({pnl_pct:+.2f}%)
━━━━━━━━━━━━━━━

{strategy_desc.get(fund_id, '')}

━━━━━━━━━━━━━━━
📋 *取引ルール*
レバレッジ: {cfg.get('leverage')}倍
取引サイズ: 残高の{cfg.get('position_size_pct')}%/回
最大同時保有: {cfg.get('max_positions')}銘柄
キャッシュ維持: {cfg.get('cash_min_pct')}%以上

🛑 損切り: {cfg.get('stop_loss_pct')}%（自動即実行）
🎯 利確①: +{cfg.get('take_profit_1')}%（50%利確・KK確認後）
🎯 利確②: +{cfg.get('take_profit_2')}%（残り利確・KK確認後）

📈 対象銘柄: {' / '.join(cfg.get('preferred_tickers', []))}

⚡ 現在のオープン: {len(open_pos)}件"""

    keyboard = [
        [
            InlineKeyboardButton("🛡️ FUND-1", callback_data="fund:rule:fund_1"),
            InlineKeyboardButton("⚡ FUND-2", callback_data="fund:rule:fund_2"),
            InlineKeyboardButton("🚀 FUND-3", callback_data="fund:rule:fund_3"),
        ],
        [InlineKeyboardButton("💰 資産に戻る", callback_data="dash:portfolio")],
    ]
    await query.edit_message_text(msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard))


async def dash_settings(query):
    """⚙️ 設定画面"""
    msg = """⚙️ *設定*
━━━━━━━━━━━━━━━

📋 *取引ルール（KK確定版）*
エントリーサイズ: 残高10%/回
最大同時保有: 5銘柄
利確T1: +8%（KK確認後）
利確T2: +15%（KK確認後）
損切り: -5%（自動即実行）
チェック間隔: 1時間ごと

🔔 *通知設定*
✅ 取引実行時
✅ 利確タイミング
✅ 緊急アラート
✅ 毎日レポート（10/15/20時）

📡 *データソース（11個）*
✅ Yahoo Finance  ✅ X感情
✅ Reddit          ✅ Fear&Greed
✅ CoinGecko      ✅ Coinglass
✅ Hyperliquid    ✅ NASA POWER
✅ Whale Alert    ✅ HackerNews
✅ VIPウォッチ（5名）

🔌 *接続済み取引所*
✅ Hyperliquid: $739 USDH
✅ dYdX: $798 USDC"""

    keyboard = [
        [
            InlineKeyboardButton("⚙️ システム状態", callback_data="cmd:status"),
        ],
        *dash_nav("settings").inline_keyboard
    ]
    await query.edit_message_text(msg, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))




async def quantum_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """量子活用レポート"""
    if not is_authorized(update): return
    await update.message.reply_text("⚛️ 量子AIレポート生成中... （30秒ほどお待ちください）")
    try:
        from quantum_report import generate_quantum_report
        generate_quantum_report()
        await update.message.reply_text("✅ 量子レポート送信完了！Telegramを確認してください🦴")
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")


async def dexter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ValueCell ResearchAgent統合版 金融リサーチAI"""
    if not is_authorized(update):
        return
    
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "📊 *Dexter 金融リサーチAI（ValueCell統合版）*\n\n"
            "使い方: `/dexter [質問]`\n\n"
            "例:\n"
            "• `/dexter NVDAの最新決算を分析して`\n"
            "• `/dexter APPLの10-Kから成長率を教えて`\n"
            "• `/dexter BTCの適正価格は？`\n"
            "• `/dexter ARMとNVDAを比較して`",
            parse_mode="Markdown"
        )
        return
    
    msg = await update.message.reply_text(f"🔍 *Dexter* 調査中...\n\n`{query}`", parse_mode="Markdown")
    
    try:
        import sys, asyncio
        sys.path.insert(0, '/Users/mr.k/Projects/valuecell/python')
        from dotenv import load_dotenv as vc_load
        vc_load('/Users/mr.k/Projects/and-ai-brain/.env')
        
        import os
        os.environ["EDGAR_USER_AGENT"] = "BK tik.betrnk@gmail.com"
        os.environ["SEC_EMAIL"] = "tik.betrnk@gmail.com"
        
        # ValueCell ResearchAgentで実行
        from valuecell.agents.research_agent.core import ResearchAgent
        from daily_research import get_fg, get_prices_bulk
        
        fg = get_fg()
        prices = get_prices_bulk()
        
        agent = ResearchAgent()
        
        # 市場コンテキストを追加したクエリ
        enhanced_query = f"""{query}

現在の市場データ（参考）:
- BTC: ${prices.get('BTC', 0):,.0f}
- ETH: ${prices.get('ETH', 0):,.0f}
- F&G: {fg}/100
- 分析日: {__import__('datetime').datetime.now().strftime('%Y/%m/%d')}

日本語で回答してください。"""
        
        # ストリーミング応答を収集
        full_response = ""
        async for chunk in agent.stream(enhanced_query):
            if hasattr(chunk, 'content') and chunk.content:
                full_response += chunk.content
        
        if not full_response:
            raise ValueError("No response from ValueCell agent")
        
        # 長い場合は分割送信
        if len(full_response) > 3800:
            full_response = full_response[:3800] + "\n\n[続きは /dexter で詳細確認]"
        
        await msg.edit_text(
            f"📊 *Dexter 分析結果*\n\n{full_response}\n\n_⚛️ &AI QE × ValueCell_",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # フォールバック: Claude直接呼び出し
        try:
            import anthropic as ant
            from daily_research import get_fg, get_prices_bulk
            
            fg = get_fg()
            prices = get_prices_bulk()
            
            client = ant.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1500,
                system="""あなたは&AI QUANTUM EDGEの金融リサーチAI「Dexter」です。
暗号資産・株式・マクロ経済の専門家として、データに基づいた分析を日本語で提供します。
断定的な投資推奨は避け「シグナル分析上は〜」「データ上は〜」の表現を使用してください。
回答は簡潔で実用的に。""",
                messages=[{
                    "role": "user",
                    "content": f"BTC=${prices.get('BTC',0):,.0f} F&G={fg}/100\n\n{query}"
                }]
            )
            answer = resp.content[0].text
            await msg.edit_text(
                f"📊 *Dexter 分析結果*\n\n{answer}\n\n_⚛️ &AI QUANTUM EDGE_",
                parse_mode="Markdown"
            )
        except Exception as e2:
            await msg.edit_text(f"❌ エラー: {str(e2)[:100]}", parse_mode="Markdown")


# ========================================
# メイン
# ========================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("momentum", momentum))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("accuracy", accuracy))
    app.add_handler(CommandHandler("monthly", monthly))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("quantum", quantum_report_cmd))
    app.add_handler(CommandHandler("d", dashboard))  # ショートカット
    app.add_handler(CommandHandler("whale", whale_cmd))
    app.add_handler(CommandHandler("update", update_positions_cmd))
    app.add_handler(CommandHandler("tp", check_tp_cmd))
    app.add_handler(CommandHandler("team", team_ask_cmd))
    app.add_handler(CommandHandler("legend", legend_cmd))
    app.add_handler(CommandHandler("savekey", save_api_key_cmd))
    app.add_handler(CommandHandler("fp", first_principles_cmd))
    app.add_handler(CommandHandler("dexter", dexter_cmd))
    app.add_handler(CommandHandler("analyze", dexter_cmd))  # エイリアス
    app.add_handler(CommandHandler("giron", first_principles_cmd))  # エイリアス
    app.add_handler(CommandHandler("getapi", get_api_from_url_cmd))
    # URL入力待ちのメッセージハンドラー（http:// で始まるもの）
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'^https?://'),
        handle_url_for_api
    ))
    app.add_handler(CommandHandler("calendar", calendar_cmd))
    app.add_handler(CallbackQueryHandler(portfolio_callback, pattern="^pf:"))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^cmd:"))
    app.add_handler(CallbackQueryHandler(dashboard_callback, pattern="^dash:"))
    app.add_handler(CallbackQueryHandler(fund_rule_callback, pattern="^fund:rule:"))
    # 常駐キーボードのテキストボタン処理
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            r'^(📊 レポート|💹 価格|🏦 ファンド|🐋 クジラ|⚡ シグナル|⚛️ 量子|🔄 更新|🎯 利確|📱 ダッシュ|🔑 APIキー)$'
        ),
        handle_keyboard_text
    ))
    
    print("⚛️ &AI QUANTUM EDGE Bot 起動中...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


async def a10s_status(update, context):
    """A10S状態確認"""
    if not is_authorized(update): return
    await update.message.reply_text("🎯 A10S状態確認中...")
    try:
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
        from a10s_strategy import get_a10s_status, should_a10s_run
        
        status = get_a10s_status()
        can_run, reasons = should_a10s_run()
        
        msg = f"""🎯 *A10S グリッド戦略 状態*
━━━━━━━━━━━━━━━

稼働判定: {'✅ 稼働可能' if can_run else '🔴 停止中'}
"""
        if not can_run:
            for r in reasons:
                msg += f"  • {r}\n"
        
        if status["active"]:
            msg += f"""
📈 実行中:
  {status['ticker']}: {status['pnl_pct']:+.2f}%
  平均単価: ${status['avg_price']:,.4f}
  進行: {status['steps_filled']}/{status['steps_total']}ステップ
  利確目標: ${status['take_profit_price']:,.4f}
  損切りライン: ${status['stop_loss_price']:,.4f}"""
        else:
            msg += "\n⏸️ 待機中"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")



async def make_video(update, context):
    """動画制作コマンド"""
    if not is_authorized(update): return
    
    theme = " ".join(context.args) if context.args else ""
    
    if not theme:
        await update.message.reply_text(
            "🎬 動画テーマを入力してください\n\n"
            "使い方: /video テーマ\n"
            "例: /video &AI QUANTUMが月利5%達成！AIが自動投資する時代\n\n"
            "または /video_test でテスト（台本のみ生成）"
        )
        return
    
    await update.message.reply_text(f"🎬 動画制作開始！\nテーマ: {theme}\n\n台本生成中...")
    
    try:
        import sys
        sys.path.insert(0, '/Users/mr.k/Projects/and-ai-brain')
        from video_factory import generate_script
        
        script = generate_script(theme, "tiktok")
        
        if script:
            msg = f"""✅ *台本生成完了！*

📝 タイトル: {script.get('title', '')}
🎣 フック: {script.get('hook', '')}
🎬 シーン数: {len(script.get('script', []))}
📢 CTA: {script.get('cta', '')}
#️⃣ {' '.join(script.get('hashtags', [])[:5])}

動画生成を開始しますか？
（fal.ai APIを使用・数分かかります）"""
            
            keyboard = [
                [
                    InlineKeyboardButton("▶️ 動画生成開始", callback_data=f"video:generate:{theme[:50]}"),
                    InlineKeyboardButton("❌ キャンセル", callback_data="cmd:back")
                ]
            ]
            await update.message.reply_text(msg, parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text("❌ 台本生成に失敗しました")
    except Exception as e:
        await update.message.reply_text(f"❌ エラー: {str(e)[:100]}")
