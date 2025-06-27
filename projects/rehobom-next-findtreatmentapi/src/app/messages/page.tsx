'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import MessageList from '@/components/messages/MessageList';
import MessageThread from '@/components/messages/MessageThread';
import { MessageThread as MessageThreadType } from '@/types/message';

export default function MessagesPage() {
  const [threads, setThreads] = useState<MessageThreadType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedThread, setSelectedThread] = useState<{
    facilityId: string;
    facilityName: string;
    messages: any[];
  } | null>(null);

  // Fetch message threads
  useEffect(() => {
    const fetchThreads = async () => {
      try {
        const response = await fetch('/api/messages');
        if (!response.ok) {
          throw new Error('Failed to fetch message threads');
        }
        const data = await response.json();
        setThreads(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
        console.error('Error fetching threads:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchThreads();
  }, []);

  // Handle thread selection
  const handleThreadSelect = async (facilityId: string) => {
    try {
      const response = await fetch(`/api/messages/${facilityId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch messages');
      }
      const data = await response.json();
      setSelectedThread({
        facilityId,
        facilityName: data.facility.name,
        messages: data.messages,
      });
    } catch (err) {
      console.error('Error fetching messages:', err);
      alert('Failed to load messages. Please try again.');
    }
  };

  // Handle sending a message
  const handleSendMessage = async (content: string) => {
    if (!selectedThread) return;

    try {
      const response = await fetch(`/api/messages/${selectedThread.facilityId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      // Refresh the thread to show the new message
      handleThreadSelect(selectedThread.facilityId);
      
      // Also refresh the threads list to update last message
      const threadsResponse = await fetch('/api/messages');
      if (threadsResponse.ok) {
        const data = await threadsResponse.json();
        setThreads(data);
      }
    } catch (err) {
      console.error('Error sending message:', err);
      alert('Failed to send message. Please try again.');
    }
  };

  return (
    <div className="py-6">
      <h1 className="text-2xl font-semibold text-green-700 mb-6">Messages</h1>
      
      {loading ? (
        <div className="bg-white rounded-lg shadow-md p-6 text-center">
          <p className="text-gray-700">Loading messages...</p>
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-red-700">{error}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            <MessageList 
              threads={threads.map(thread => ({
                facilityId: thread.facilityId,
                facilityName: thread.facilityName,
                lastMessage: thread.lastMessage,
                unreadCount: thread.unreadCount,
              }))}
              onThreadSelect={handleThreadSelect}
              selectedThreadId={selectedThread?.facilityId}
            />
          </div>
          
          <div className="md:col-span-2">
            {selectedThread ? (
              <MessageThread 
                facilityName={selectedThread.facilityName}
                messages={selectedThread.messages}
                onSendMessage={handleSendMessage}
              />
            ) : (
              <div className="bg-white rounded-lg shadow-md p-6 h-full flex items-center justify-center">
                <p className="text-gray-500">Select a conversation to view messages</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
