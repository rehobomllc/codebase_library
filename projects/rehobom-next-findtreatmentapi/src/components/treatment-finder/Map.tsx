'use client';

import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Component to update map view when center changes
function ChangeView({ center, zoom }: { center: { lat: number; lng: number }, zoom: number }) {
  const map = useMap();
  
  useEffect(() => {
    map.setView([center.lat, center.lng], zoom);
  }, [center, zoom, map]);
  
  return null;
}

interface MapProps {
  center?: { lat: number; lng: number };
  markers?: Array<{
    position: { lat: number; lng: number };
    title: string;
    id: string;
  }>;
  onMarkerClick?: (id: string) => void;
  zoom?: number;
}

export default function Map({ 
  center = { lat: 39.8283, lng: -98.5795 }, // Center of US
  markers = [],
  onMarkerClick,
  zoom = 4
}: MapProps) {
  // Fix Leaflet icon issue in Next.js
  useEffect(() => {
    // Only run this code in the browser
    if (typeof window !== 'undefined') {
      // Fix the default icon issue
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png',
      });
    }
  }, []);

  // Handle marker click events
  const handleMarkerClick = (id: string) => {
    if (onMarkerClick) {
      onMarkerClick(id);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4 mb-4">
      <div className="w-full h-64 rounded-md" style={{ minHeight: '250px' }}>
        <MapContainer 
          center={[center.lat, center.lng]} 
          zoom={zoom} 
          style={{ height: '100%', width: '100%' }}
          zoomControl={true}
          scrollWheelZoom={false}
        >
          <ChangeView center={center} zoom={zoom} />
          
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          
          {markers.map((marker) => (
            <Marker 
              key={marker.id}
              position={[marker.position.lat, marker.position.lng]}
              eventHandlers={{
                click: () => handleMarkerClick(marker.id),
              }}
            >
              <Popup>
                {marker.title}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
