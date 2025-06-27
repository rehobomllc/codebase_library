'use client';

import { useState } from 'react';
import { Message } from '@/types/message';

interface MessageListProps {
  threads: Array<{
    facilityId: string;
    facilityName: string;
    lastMessage?: Message;
    unreadCount: number;
  }>;
  onThreadSelect: (facilityId: string) => void;
  selectedThreadId?: string;
}

export default function MessageList({ 
  threads, 
  onThreadSelect,
  selectedThreadId
}: MessageListProps) {
  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <h2 className="text-lg font-semibold text-gray-800 p-4 border-b">Messages</h2>
      
      {threads.length === 0 ? (
        <div className="p-6 text-center text-gray-500">
          No messages yet. Contact a facility to start a conversation.
        </div>
      ) : (
        <ul className="divide-y divide-gray-200">
          {threads.map((thread) => (
            <li 
              key={thread.facilityId}
              className={`cursor-pointer hover:bg-gray-50 ${
                selectedThreadId === thread.facilityId ? 'bg-green-50' : ''
              }`}
              onClick={() => onThreadSelect(thread.facilityId)}
            >
              <div className="p-4">
                <div className="flex justify-between items-start">
                  <h3 className="text-md font-medium text-gray-800">{thread.facilityName}</h3>
                  {thread.unreadCount > 0 && (
                    <span className="bg-green-500 text-white text-xs font-bold px-2 py-1 rounded-full">
                      {thread.unreadCount}
                    </span>
                  )}
                </div>
                
                {thread.lastMessage && (
                  <p className="text-sm text-gray-600 mt-1 truncate">
                    {thread.lastMessage.content}
                  </p>
                )}
                
                {thread.lastMessage && (
                  <p className="text-xs text-gray-400 mt-1">
                    {new Date(thread.lastMessage.createdAt).toLocaleDateString()}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
