'use client';

import FloatingAIChat from '@/components/FloatingAIChat';

export default function AdminLayout({
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
