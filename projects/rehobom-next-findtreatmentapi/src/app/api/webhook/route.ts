import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { receiveMessage } from '@/lib/db/message';

export async function POST(request: Request) {
  try {
    const data = await request.json();
    
    // Validate webhook payload
    if (!data.facilityId || !data.content || !data.email) {
      return NextResponse.json({ error: 'Invalid payload. Required fields: facilityId, content, email' }, { status: 400 });
    }
    
    // Find the facility by ID
    const facility = await prisma.facility.findUnique({
      where: {
        id: data.facilityId,
      },
    });
    
    if (!facility) {
      return NextResponse.json({ error: 'Facility not found' }, { status: 404 });
    }
    
    // Store the incoming message
    const message = await receiveMessage(data.facilityId, data.content);
    
    return NextResponse.json({ 
      success: true, 
      messageId: message.id,
      facilityName: facility.name
    });
  } catch (error) {
    console.error('Webhook error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
