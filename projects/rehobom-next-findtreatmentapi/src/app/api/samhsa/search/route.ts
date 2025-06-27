import { NextResponse } from 'next/server';
import { searchByAddress } from '@/lib/api/samhsa';

export async function GET(request: Request) {
  try {
    // Get search parameters from URL
    const { searchParams } = new URL(request.url);
    
    const address = searchParams.get('address');
    const distance = searchParams.get('distance');
    const services = searchParams.get('services');
    const sType = searchParams.get('sType');
    
    if (!address) {
      return NextResponse.json(
        { error: 'Address parameter is required' },
        { status: 400 }
      );
    }
    
    // Parse additional parameters
    const additionalParams: Record<string, string> = {};
    if (services) {
      additionalParams.sCodes = services;
    }
    if (sType) {
      additionalParams.sType = sType;
    }
    
    // Add any other parameters that were passed
    searchParams.forEach((value, key) => {
      if (!['address', 'distance', 'services', 'sType'].includes(key)) {
        additionalParams[key] = value;
      }
    });
    
    // Call the enhanced search function
    const results = await searchByAddress(
      address,
      distance ? parseInt(distance) : 50,
      additionalParams
    );
    
    return NextResponse.json(results);
  } catch (error) {
    console.error('Error searching facilities by address:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'An error occurred' },
      { status: 500 }
    );
  }
}
