#!/usr/bin/env bun
/**
 * Telegram gateway for bk-dexter
 * Polls Telegram for messages and routes them through the Dexter agent.
 */

import { monitorTelegramChannel } from './channels/telegram/index.js';
import { sendMessageTelegram } from './channels/telegram/outbound.js';
import type { TelegramInboundMessage } from './channels/telegram/types.js';
import { runAgentForMessage } from './agent-runner.js';

// Load env
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const ALLOWED_FROM_RAW = process.env.TELEGRAM_ALLOWED_FROM ?? '';
const ACCOUNT_ID = process.env.TELEGRAM_ACCOUNT_ID ?? 'andai-qe';

if (!BOT_TOKEN) {
  console.error('[telegram-dexter] ERROR: TELEGRAM_BOT_TOKEN is not set in .env');
  process.exit(1);
}

const ALLOWED_FROM = ALLOWED_FROM_RAW
  ? ALLOWED_FROM_RAW.split(',').map((s) => s.trim()).filter(Boolean)
  : [];

const HELP_TEXT = `🤖 *Dexter Bot コマンド一覧*

/dexter [質問] — Dexterに質問する
例: /dexter BTCの適正価格は？

/analyze [銘柄] — 銘柄の最新分析
例: /analyze BTC
例: /analyze AAPL

/help — このヘルプを表示

その他のテキスト → Dexterに直接渡します`;

async function handleMessage(msg: TelegramInboundMessage): Promise<void> {
  const { chatId, text, userId } = msg;
  const trimmed = text.trim();

  console.log(`[telegram-dexter] Message from ${userId} in ${chatId}: "${trimmed.slice(0, 80)}"`);

  let query: string;

  if (trimmed === '/help' || trimmed === '/help@andaibraincommandbot') {
    await sendMessageTelegram({ botToken: BOT_TOKEN!, chatId, text: HELP_TEXT });
    return;
  } else if (trimmed.startsWith('/dexter ')) {
    query = trimmed.slice('/dexter '.length).trim();
  } else if (trimmed === '/dexter' || trimmed === '/dexter@andaibraincommandbot') {
    await sendMessageTelegram({
      botToken: BOT_TOKEN!,
      chatId,
      text: '使い方: `/dexter [質問]`\n例: `/dexter BTCの適正価格は？`',
    });
    return;
  } else if (trimmed.startsWith('/analyze ')) {
    const symbol = trimmed.slice('/analyze '.length).trim().toUpperCase();
    query = `${symbol}の最新分析をしてください`;
  } else if (trimmed === '/analyze' || trimmed === '/analyze@andaibraincommandbot') {
    await sendMessageTelegram({
      botToken: BOT_TOKEN!,
      chatId,
      text: '使い方: `/analyze [銘柄]`\n例: `/analyze BTC`',
    });
    return;
  } else if (trimmed.startsWith('/')) {
    // Unknown command — skip silently
    return;
  } else {
    // Plain text → pass directly to Dexter
    query = trimmed;
  }

  if (!query) return;

  // Typing indicator (best-effort)
  try {
    const { default: axios } = await import('axios');
    await axios.post(`https://api.telegram.org/bot${BOT_TOKEN}/sendChatAction`, {
      chat_id: chatId,
      action: 'typing',
    });
  } catch {
    // ignore
  }

  try {
    const sessionKey = `agent:dexter:telegram:${ACCOUNT_ID}:direct:${userId}`;
    const answer = await runAgentForMessage({
      sessionKey,
      query,
      model: process.env.DEXTER_MODEL ?? 'claude-haiku-4-5',
      modelProvider: process.env.DEXTER_MODEL_PROVIDER ?? 'anthropic',
      maxIterations: 10,
      channel: 'telegram',
    });

    const replyText = answer || '（回答を取得できませんでした）';
    await sendMessageTelegram({ botToken: BOT_TOKEN!, chatId, text: replyText });
  } catch (err) {
    console.error('[telegram-dexter] Agent error:', err);
    await sendMessageTelegram({
      botToken: BOT_TOKEN!,
      chatId,
      text: `⚠️ エラーが発生しました: ${String(err).slice(0, 200)}`,
    });
  }
}

async function main() {
  console.log(`[telegram-dexter] Starting. accountId=${ACCOUNT_ID}, allowFrom=${ALLOWED_FROM.join(',') || 'all'}`);

  const abortController = new AbortController();

  process.on('SIGINT', () => {
    console.log('[telegram-dexter] SIGINT received, shutting down...');
    abortController.abort();
  });
  process.on('SIGTERM', () => {
    console.log('[telegram-dexter] SIGTERM received, shutting down...');
    abortController.abort();
  });

  await monitorTelegramChannel({
    accountId: ACCOUNT_ID,
    botToken: BOT_TOKEN!,
    allowFrom: ALLOWED_FROM,
    verbose: true,
    abortSignal: abortController.signal,
    onMessage: handleMessage,
    onStatus: (status) => {
      if (status.connected) {
        console.log('[telegram-dexter] Connected ✅');
      } else {
        console.error(`[telegram-dexter] Disconnected: ${status.lastError}`);
      }
    },
  });

  console.log('[telegram-dexter] Stopped.');
}

main().catch((err) => {
  console.error('[telegram-dexter] Fatal error:', err);
  process.exit(1);
});
