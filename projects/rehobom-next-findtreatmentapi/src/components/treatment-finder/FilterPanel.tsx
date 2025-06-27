'use client';

import { useState } from 'react';
import { SearchParams } from '@/lib/api/samhsa';

interface FilterPanelProps {
  onFilterChange: (filters: SearchParams) => void;
}

export default function FilterPanel({ onFilterChange }: FilterPanelProps) {
  const [filters, setFilters] = useState<SearchParams>({
    limitType: 2, // Default to distance search
    limitValue: '80467.2', // 50 miles in meters
    pageSize: 100,
    page: 1,
    sort: 0, // Sort by distance
  });

  const [selectedServices, setSelectedServices] = useState<string[]>([]);

  const serviceOptions = [
    { code: 'SA', label: 'Substance Abuse Treatment' },
    { code: 'MH', label: 'Mental Health Treatment' },
    { code: 'DET', label: 'Detoxification' },
    { code: 'OP', label: 'Outpatient Services' },
    { code: 'RES', label: 'Residential Treatment' },
    { code: 'HI', label: 'Hospital Inpatient' },
    { code: 'MAT', label: 'Medication-Assisted Treatment' },
    { code: 'BU', label: 'Buprenorphine' },
    { code: 'NU', label: 'Naltrexone' },
    { code: 'OTP', label: 'Opioid Treatment Program' },
    { code: 'DM', label: 'Methadone Detoxification' },
    { code: 'MM', label: 'Methadone Maintenance' },
  ];

  const handleServiceToggle = (code: string) => {
    setSelectedServices(prev => {
      const newServices = prev.includes(code)
        ? prev.filter(s => s !== code)
        : [...prev, code];
      
      // Update filters with new services
      const newFilters = {
        ...filters,
        sCodes: newServices.length > 0 ? newServices.join(',') : undefined,
      };
      
      setFilters(newFilters);
      onFilterChange(newFilters);
      
      return newServices;
    });
  };

  const handleDistanceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const distanceInMiles = parseInt(e.target.value);
    const distanceInMeters = (distanceInMiles * 1609.34).toFixed(1);
    
    const newFilters = {
      ...filters,
      limitValue: distanceInMeters,
    };
    
    setFilters(newFilters);
    onFilterChange(newFilters);
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Filter Options</h2>
      
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Distance
        </label>
        <select 
          className="w-full p-2 border border-gray-300 rounded-md"
          onChange={handleDistanceChange}
          defaultValue="50"
        >
          <option value="10">10 miles</option>
          <option value="25">25 miles</option>
          <option value="50">50 miles</option>
          <option value="100">100 miles</option>
        </select>
      </div>
      
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Services
        </label>
        <div className="grid grid-cols-2 gap-2">
          {serviceOptions.map(service => (
            <div key={service.code} className="flex items-center">
              <input
                type="checkbox"
                id={`service-${service.code}`}
                checked={selectedServices.includes(service.code)}
                onChange={() => handleServiceToggle(service.code)}
                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
              />
              <label 
                htmlFor={`service-${service.code}`}
                className="ml-2 text-sm text-gray-700"
              >
                {service.label}
              </label>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
