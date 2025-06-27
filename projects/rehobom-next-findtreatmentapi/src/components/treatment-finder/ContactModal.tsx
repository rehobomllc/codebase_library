'use client';

import { useState } from 'react';
import { Facility } from '@/types/facility';

interface ContactModalProps {
  facility: Facility | null;
  onClose: () => void;
  onSend: (facilityId: string, message: string) => Promise<void>;
}

export default function ContactModal({ facility, onClose, onSend }: ContactModalProps) {
  const [message, setMessage] = useState('I am interested in learning more about your services.');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  if (!facility) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!message.trim()) {
      setError('Please enter a message');
      return;
    }
    
    setSending(true);
    setError(null);
    
    try {
      await onSend(facility.id, message.trim());
      setSuccess(true);
    } catch (err) {
      setError('Failed to send message. Please try again.');
      console.error('Error sending message:', err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            Contact {facility.name}
          </h2>
          
          {success ? (
            <div className="text-center py-6">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-green-500 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <p className="text-gray-700 mb-4">Your message has been sent!</p>
              <p className="text-gray-600 text-sm mb-6">
                The facility will receive your message and respond via the Messages section of this app.
              </p>
              <button
                onClick={onClose}
                className="bg-green-500 text-white px-4 py-2 rounded-md hover:bg-green-600 transition-colors"
              >
                View Messages
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label htmlFor="message" className="block text-sm font-medium text-gray-700 mb-2">
                  Message
                </label>
                <textarea
                  id="message"
                  rows={4}
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-green-500 focus:border-green-500"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  disabled={sending}
                />
              </div>
              
              {error && (
                <div className="mb-4 text-red-500 text-sm">
                  {error}
                </div>
              )}
              
              <div className="flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
                  disabled={sending}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="bg-green-500 text-white px-4 py-2 rounded-md hover:bg-green-600 transition-colors disabled:bg-green-300"
                  disabled={sending}
                >
                  {sending ? 'Sending...' : 'Send Message'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
