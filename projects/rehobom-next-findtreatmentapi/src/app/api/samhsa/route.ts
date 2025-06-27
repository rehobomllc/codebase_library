import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    // Get search parameters from URL
    const { searchParams } = new URL(request.url);
    
    // Convert searchParams to query string
    const queryString = searchParams.toString();
    
    // Build the URL for the SAMHSA API
    const apiUrl = `https://findtreatment.gov/locator/exportsAsJson/v2?${queryString}`;
    
    // Call the SAMHSA API from the server (no CORS issues)
    const response = await fetch(apiUrl, {
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }
    
    const results = await response.json();
    
    return NextResponse.json(results);
  } catch (error) {
    console.error('Error searching facilities:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'An error occurred' },
      { status: 500 }
    );
  }
}
