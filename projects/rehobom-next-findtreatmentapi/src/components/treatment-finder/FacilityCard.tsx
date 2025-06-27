'use client';

import { useState } from 'react';
import { Facility } from '@/types/facility';

interface FacilityCardProps {
  facility: Facility;
  onContactClick: (facility: Facility) => void;
}

export default function FacilityCard({ facility, onContactClick }: FacilityCardProps) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div 
      className={`bg-white rounded-lg shadow-md p-4 mb-4 transition-all duration-300 ${
        expanded ? 'h-auto' : 'h-32 overflow-hidden'
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex justify-between items-start">
        <h3 className="text-lg font-semibold text-gray-800">{facility.name}</h3>
        {facility.distance && (
          <span className="text-sm text-gray-500">{facility.distance.toFixed(1)} miles</span>
        )}
      </div>
      
      <p className="text-gray-600 text-sm mt-1">
        {facility.address}, {facility.city}, {facility.state} {facility.zip}
      </p>
      
      {facility.phone && (
        <p className="text-gray-600 text-sm mt-1">
          {facility.phone}
        </p>
      )}
      
      {expanded && (
        <div className="mt-4">
          <h4 className="text-md font-medium text-gray-700 mb-2">Services</h4>
          <ul className="text-sm text-gray-600">
            {facility.services && facility.services.map((service, index) => (
              <li key={index} className="mb-1">
                <span className="font-medium">{service.f1}:</span> {service.f3}
              </li>
            ))}
          </ul>
          
          <button
            className="mt-4 bg-green-500 text-white px-4 py-2 rounded-full flex items-center justify-center"
            onClick={(e) => {
              e.stopPropagation();
              onContactClick(facility);
            }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            Contact
          </button>
        </div>
      )}
    </div>
  );
}
