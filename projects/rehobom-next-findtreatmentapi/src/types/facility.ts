export interface Facility {
  id: string;
  facilityId: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  phone?: string;
  email?: string;
  website?: string;
  latitude?: number;
  longitude?: number;
  distance?: number;
  services: Array<{
    f1: string; // Service category
    f2: string; // Service code
    f3: string; // Service description
  }>;
}

export interface FacilitySearchResponse {
  page: number;
  totalPages: number;
  recordCount: number;
  rows: Facility[];
}
