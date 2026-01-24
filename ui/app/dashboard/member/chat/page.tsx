'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * AI Chat is now available as a floating widget on all member pages.
 * Redirect /dashboard/member/chat to the member dashboard.
 */
export default function ChatRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/dashboard/member');
  }, [router]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 flex items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600" />
    </div>
  );
}
