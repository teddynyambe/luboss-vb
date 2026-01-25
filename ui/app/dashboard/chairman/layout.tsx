'use client';

import FloatingAIChat from '@/components/FloatingAIChat';

export default function ChairmanLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {children}
      <FloatingAIChat />
    </>
  );
}
