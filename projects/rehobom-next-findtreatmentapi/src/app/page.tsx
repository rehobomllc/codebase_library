'use client';

import { useState, useEffect } from 'react';
import { Facility, FacilitySearchResponse } from '@/types/facility';
import { SearchParams, searchFacilities } from '@/lib/api/samhsa';
import { createFacility } from '@/lib/db/facility';
import { sendMessage } from '@/lib/db/message';

import SearchBar from '@/components/treatment-finder/SearchBar';
import FilterPanel from '@/components/treatment-finder/FilterPanel';
import Map from '@/components/treatment-finder/Map';
import FacilityCard from '@/components/treatment-finder/FacilityCard';

export default function TreatmentFinder() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useState<SearchParams>({
    limitType: 2, // Default to distance search
    limitValue: '80467.2', // 50 miles in meters
    pageSize: 100,
    page: 1,
    sort: 0, // Sort by distance
  });
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);

  // Handle search by location
  const handleSearch = async (location: string) => {
    setLoading(true);
    setError(null);
    
    try {
      // First, geocode the location using Nominatim (OpenStreetMap) geocoding service
      const geocodeUrl = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(location)}&limit=1`;
      const geocodeResponse = await fetch(geocodeUrl, {
        headers: {
          'Accept-Language': 'en-US,en;q=0.9',
          'User-Agent': 'TreatmentFinderCompanionApp/1.0' // Nominatim requires a User-Agent
        }
      });
      const geocodeData = await geocodeResponse.json();
      
      if (!geocodeData || geocodeData.length === 0) {
        throw new Error('Location not found. Please try a different search term.');
      }
      
      const lat = parseFloat(geocodeData[0].lat);
      const lng = parseFloat(geocodeData[0].lon);
      setCenter({ lat, lng });
      
      // Update search params with new coordinates
      // Format coordinates according to API requirements: "{lng},{lat}"
      const newParams = {
        ...searchParams,
        sAddr: `${lng},${lat}`, // API expects longitude,latitude format
      };
      
      setSearchParams(newParams);
      
      // Search for facilities
      const response = await searchFacilities(newParams);
      setFacilities(response.rows || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred during search');
      console.error('Search error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Handle filter changes
  const handleFilterChange = (filters: SearchParams) => {
    setSearchParams((prev: SearchParams) => ({
      ...prev,
      ...filters,
    }));
  };

  // Search for facilities when search params change and we have coordinates
  useEffect(() => {
    if (searchParams.sAddr) {
      const fetchFacilities = async () => {
        setLoading(true);
        setError(null);
        
        try {
          const response = await searchFacilities(searchParams);
          setFacilities(response.rows || []);
        } catch (err) {
          setError(err instanceof Error ? err.message : 'An error occurred during search');
          console.error('Search error:', err);
        } finally {
          setLoading(false);
        }
      };
      
      fetchFacilities();
    }
  }, [searchParams]);

  // Handle contact button click
  const handleContactClick = async (facility: Facility) => {
    try {
      // First, save the facility to our database
      const savedFacility = await createFacility({
        facilityId: facility.id,
        name: facility.name,
        address: facility.address, // Use address instead of street1
        city: facility.city,
        state: facility.state,
        zip: facility.zip,
        phone: facility.phone,
        email: facility.email,
        website: facility.website,
        latitude: facility.latitude ? Number(facility.latitude) : 0,
        longitude: facility.longitude ? Number(facility.longitude) : 0,
        services: facility.services,
      });
      
      // Then, send an initial message
      await sendMessage(savedFacility.id, 'I am interested in learning more about your services.');
      
      // Redirect to the messages page for this facility
      window.location.href = `/messages/${savedFacility.id}`;
    } catch (err) {
      console.error('Error contacting facility:', err);
      alert('There was an error contacting this facility. Please try again later.');
    }
  };

  return (
    <div className="py-6">
      <h1 className="text-2xl font-semibold text-green-700 mb-6">Find Treatment Facilities</h1>
      
      <SearchBar onSearch={handleSearch} />
      
      <FilterPanel onFilterChange={handleFilterChange} />
      
      {center && (
        <Map 
          center={center}
          markers={facilities.map(facility => ({
            position: { 
              lat: facility.latitude ? Number(facility.latitude) : 0, 
              lng: facility.longitude ? Number(facility.longitude) : 0
            },
            title: facility.name,
            id: facility.id,
          }))}
          zoom={10}
        />
      )}
      
      {loading && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-4 text-center">
          <p className="text-gray-700">Searching for facilities...</p>
        </div>
      )}
      
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-4">
          <p className="text-red-700">{error}</p>
        </div>
      )}
      
      {!loading && !error && facilities.length === 0 && searchParams.sAddr && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-4">
          <p className="text-gray-700">No facilities found matching your criteria. Try adjusting your filters or search location.</p>
        </div>
      )}
      
      {!loading && facilities.length > 0 && (
        <div className="mt-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            {facilities.length} Facilities Found
          </h2>
          
          <div className="space-y-4">
            {facilities.map(facility => (
              <FacilityCard 
                key={facility.id}
                facility={facility}
                onContactClick={handleContactClick}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
