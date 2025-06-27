'use client';

import { useState } from 'react';

interface SearchBarProps {
  onSearch: (location: string) => void;
}

export default function SearchBar({ onSearch }: SearchBarProps) {
  const [searchInput, setSearchInput] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      onSearch(searchInput.trim());
    }
  };
  
  return (
    <div className="bg-white rounded-lg shadow-md p-4 mb-4">
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          placeholder="Enter city, state, or zip code"
          className="flex-1 p-2 border border-gray-300 rounded-md focus:ring-green-500 focus:border-green-500"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button
          type="submit"
          className="bg-green-500 text-white px-4 py-2 rounded-md hover:bg-green-600 transition-colors"
        >
          Search
        </button>
      </form>
    </div>
  );
}
