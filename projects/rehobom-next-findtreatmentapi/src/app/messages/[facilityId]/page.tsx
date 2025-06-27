'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import MessageThread from '@/components/messages/MessageThread';

export default function FacilityMessagePage() {
  const params = useParams();
  const facilityId = params.facilityId as string;
  
  const [threadData, setThreadData] = useState<{
    facility: {
      id: string;
      name: string;
    };
    messages: any[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch facility messages
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        const response = await fetch(`/api/messages/${facilityId}`);
        if (!response.ok) {
          throw new Error('Failed to fetch messages');
        }
        const data = await response.json();
        setThreadData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
        console.error('Error fetching messages:', err);
      } finally {
        setLoading(false);
      }
    };

    if (facilityId) {
      fetchMessages();
    }
  }, [facilityId]);

  // Handle sending a message
  const handleSendMessage = async (content: string) => {
    try {
      const response = await fetch(`/api/messages/${facilityId}`, {
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
      const refreshResponse = await fetch(`/api/messages/${facilityId}`);
      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        setThreadData(data);
      }
    } catch (err) {
      console.error('Error sending message:', err);
      alert('Failed to send message. Please try again.');
    }
  };

  return (
    <div className="py-6 h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-semibold text-green-700 mb-6">
        {threadData ? `Messages with ${threadData.facility.name}` : 'Messages'}
      </h1>
      
      {loading ? (
        <div className="bg-white rounded-lg shadow-md p-6 text-center">
          <p className="text-gray-700">Loading messages...</p>
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-red-700">{error}</p>
        </div>
      ) : threadData ? (
        <div className="h-[calc(100vh-12rem)]">
          <MessageThread 
            facilityName={threadData.facility.name}
            messages={threadData.messages}
            onSendMessage={handleSendMessage}
          />
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-md p-6 text-center">
          <p className="text-gray-700">Facility not found</p>
        </div>
      )}
    </div>
  );
}
