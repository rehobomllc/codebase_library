'use client';

import Image from 'next/image';

export default function Header() {
  return (
    <header className="flex justify-center items-center py-4">
      <div className="w-40 h-12 relative">
        <Image 
          src="/logo.png" 
          alt="Treatment Finder Logo" 
          fill
          style={{ objectFit: 'contain' }}
          priority
        />
      </div>
    </header>
  );
}
