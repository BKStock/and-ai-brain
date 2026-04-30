import axios from 'axios';
import type { TelegramInboundMessage } from './types.js';

export async function monitorTelegramChannel(params: {
  accountId: string;
  botToken: string;
  allowFrom: string[];
  verbose: boolean;
  abortSignal: AbortSignal;
  onMessage: (msg: TelegramInboundMessage) => Promise<void>;
  onStatus?: (status: { connected: boolean; lastError?: string | null }) => void;
}): Promise<void> {
  const { botToken, allowFrom, verbose, abortSignal } = params;
  let offset = 0;
  params.onStatus?.({ connected: true, lastError: null });

  while (!abortSignal.aborted) {
    try {
      const res = await axios.get(
        `https://api.telegram.org/bot${botToken}/getUpdates`,
        { params: { offset, timeout: 30, allowed_updates: ['message'] }, timeout: 35000 }
      );
      const updates = res.data.result || [];
      for (const update of updates) {
        offset = update.update_id + 1;
        const msg = update.message;
        if (!msg?.text) continue;
        const chatId = String(msg.chat.id);
        const userId = String(msg.from?.id || '');
        if (allowFrom.length > 0 && !allowFrom.includes(chatId) && !allowFrom.includes(userId)) {
          if (verbose) console.log(`[telegram] blocked: ${chatId}`);
          continue;
        }
        await params.onMessage({
          accountId: params.accountId,
          chatId,
          userId,
          text: msg.text,
          messageId: msg.message_id,
          timestamp: new Date(msg.date * 1000),
        });
      }
    } catch (err: unknown) {
      if (abortSignal.aborted) break;
      const errStr = String(err);
      // 409: 他のポーリングセッションが残っている → 少し待ってリトライ
      if (errStr.includes('409')) {
        if (verbose) console.log('[telegram] 409 Conflict - waiting 10s for other session to close...');
        await new Promise(r => setTimeout(r, 10000));
        continue;
      }
      if (verbose) console.error('[telegram] polling error:', err);
      params.onStatus?.({ connected: false, lastError: errStr });
      await new Promise(r => setTimeout(r, 5000));
      params.onStatus?.({ connected: true, lastError: null });
    }
  }
}
