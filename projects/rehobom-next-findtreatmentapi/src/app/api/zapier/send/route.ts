import { NextResponse } from 'next/server';
import { sendMessage } from '@/lib/db/message';

export async function POST(request: Request) {
  try {
    const data = await request.json();
    
    // Validate request body
    if (!data.facilityId || !data.content) {
      return NextResponse.json({ error: 'Missing required fields: facilityId, content' }, { status: 400 });
    }
    
    // Send the message
    const message = await sendMessage(data.facilityId, data.content);
    
    // Here we would trigger the Zapier workflow to send an email
    // This would typically be done by making a request to a Zapier webhook URL
    
    // Example of how to trigger a Zapier webhook (commented out as we don't have the actual URL)
    /*
    await fetch('https://hooks.zapier.com/hooks/catch/your-zapier-webhook-id', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        facilityId: data.facilityId,
        content: data.content,
        messageId: message.id,
        timestamp: new Date().toISOString(),
      }),
    });
    */
    
    return NextResponse.json({ 
      success: true, 
      messageId: message.id,
      message: 'Message sent successfully. Zapier workflow will be triggered to send an email.'
    });
  } catch (error) {
    console.error('Error sending message:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
