import axios from 'axios';

export async function sendMessageTelegram(params: {
  botToken: string;
  chatId: string;
  text: string;
  parseMode?: 'Markdown' | 'HTML';
}): Promise<void> {
  const { botToken, chatId, text } = params;
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += 4000) {
    chunks.push(text.slice(i, i + 4000));
  }
  for (const chunk of chunks) {
    try {
      await axios.post(
        `https://api.telegram.org/bot${botToken}/sendMessage`,
        { chat_id: chatId, text: chunk, parse_mode: 'Markdown', disable_web_page_preview: true },
        { timeout: 15000 }
      );
    } catch {
      await axios.post(
        `https://api.telegram.org/bot${botToken}/sendMessage`,
        { chat_id: chatId, text: chunk },
        { timeout: 15000 }
      );
    }
  }
}
