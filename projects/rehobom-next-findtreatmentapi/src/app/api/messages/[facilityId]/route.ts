import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: { facilityId: string } }
) {
  try {
    // For deployment purposes, we'll return a mock response
    return NextResponse.json({
      facility: {
        id: params.facilityId,
        name: "Sample Treatment Center",
        address: "123 Main Street",
        city: "Anytown",
        state: "CA",
        zip: "12345",
        phone: "555-123-4567",
      },
      messages: [
        {
          id: "msg1",
          facilityId: params.facilityId,
          direction: "outgoing",
          content: "I am interested in learning more about your services.",
          read: true,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        },
        {
          id: "msg2",
          facilityId: params.facilityId,
          direction: "incoming",
          content: "Thank you for your interest. We offer a variety of treatment options. Would you like to schedule a consultation?",
          read: true,
          createdAt: new Date(Date.now() + 3600000).toISOString(),
          updatedAt: new Date(Date.now() + 3600000).toISOString()
        }
      ],
    });
  } catch (error) {
    console.error('Error fetching facility messages:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { facilityId: string } }
) {
  try {
    const data = await request.json();

    // Validate request body
    if (!data.content) {
      return NextResponse.json({ error: 'Message content is required' }, { status: 400 });
    }

    // For deployment purposes, we'll return a mock response
    return NextResponse.json({ 
      success: true, 
      messageId: "new-msg-" + Date.now(),
      message: "Message sent successfully."
    });
  } catch (error) {
    console.error('Error sending message:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
