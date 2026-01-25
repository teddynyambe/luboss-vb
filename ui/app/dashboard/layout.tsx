'use client';

import FloatingAIChat from '@/components/FloatingAIChat';

export default function DashboardLayout({
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
