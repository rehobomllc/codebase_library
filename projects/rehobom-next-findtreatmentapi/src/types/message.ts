export interface Message {
  id: string;
  facilityId: string;
  direction: 'incoming' | 'outgoing';
  content: string;
  read: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface MessageThread {
  facilityId: string;
  facilityName: string;
  messages: Message[];
  unreadCount: number;
  lastMessageDate: Date;
}
