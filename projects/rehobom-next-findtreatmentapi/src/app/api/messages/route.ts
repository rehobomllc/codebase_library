import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

// GET /api/messages - Get all message threads
export async function GET() {
  try {
    // Get all facilities that have messages
    const facilities = await prisma.facility.findMany({
      where: {
        messages: {
          some: {}
        }
      },
      include: {
        messages: {
          orderBy: {
            createdAt: 'desc'
          },
          take: 1
        },
        _count: {
          select: {
            messages: {
              where: {
                read: false,
                direction: 'incoming'
              }
            }
          }
        }
      }
    });

    // Format the response
    const threads = facilities.map(facility => ({
      facilityId: facility.id,
      facilityName: facility.name,
      lastMessage: facility.messages[0],
      unreadCount: facility._count.messages,
      lastMessageDate: facility.messages[0]?.createdAt
    }));

    // Sort by most recent message
    threads.sort((a, b) => {
      if (!a.lastMessageDate) return 1;
      if (!b.lastMessageDate) return -1;
      return b.lastMessageDate.getTime() - a.lastMessageDate.getTime();
    });

    return NextResponse.json(threads);
  } catch (error) {
    console.error('Error fetching messages:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
