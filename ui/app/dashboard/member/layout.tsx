'use client';

import FloatingAIChat from '@/components/FloatingAIChat';

export default function MemberLayout({
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
