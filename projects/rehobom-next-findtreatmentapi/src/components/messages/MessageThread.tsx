'use client';

import { useState, useRef, useEffect } from 'react';
import { Message } from '@/types/message';

interface MessageThreadProps {
  facilityName: string;
  messages: Message[];
  onSendMessage: (content: string) => void;
}

export default function MessageThread({ 
  facilityName, 
  messages, 
  onSendMessage 
}: MessageThreadProps) {
  const [newMessage, setNewMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (newMessage.trim()) {
      onSendMessage(newMessage.trim());
      setNewMessage('');
    }
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="bg-white rounded-lg shadow-md flex flex-col h-full">
      <div className="p-4 border-b">
        <h2 className="text-lg font-semibold text-gray-800">{facilityName}</h2>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            No messages yet. Start the conversation by sending a message.
          </div>
        ) : (
          messages.map((message) => (
            <div 
              key={message.id}
              className={`max-w-[80%] p-3 rounded-lg ${
                message.direction === 'outgoing' 
                  ? 'bg-green-100 ml-auto rounded-tr-none' 
                  : 'bg-gray-100 mr-auto rounded-tl-none'
              }`}
            >
              <p className="text-gray-800">{message.content}</p>
              <p className="text-xs text-gray-500 mt-1 text-right">
                {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form onSubmit={handleSubmit} className="p-4 border-t flex">
        <input
          type="text"
          placeholder="Type your message..."
          className="flex-1 p-2 border border-gray-300 rounded-l-md focus:ring-green-500 focus:border-green-500"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
        />
        <button
          type="submit"
          className="bg-green-500 text-white px-4 py-2 rounded-r-md hover:bg-green-600 transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
}
