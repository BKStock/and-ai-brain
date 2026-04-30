export interface TelegramInboundMessage {
  accountId: string;
  chatId: string;
  userId: string;
  text: string;
  messageId: number;
  timestamp: Date;
}
