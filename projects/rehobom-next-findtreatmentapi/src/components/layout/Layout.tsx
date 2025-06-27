'use client';

import BottomNavigation from './BottomNavigation';
import Header from './Header';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Header />
      <main className="flex-1 container mx-auto px-4 pb-20">
        {children}
      </main>
      <BottomNavigation />
    </div>
  );
}
