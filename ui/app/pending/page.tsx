'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import Link from 'next/link';

export default function PendingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user?.approved) {
      router.push('/dashboard');
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="mt-4 text-blue-700 text-lg">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 py-8 px-4">
      <div className="max-w-md w-full space-y-6 md:space-y-8 text-center">
        <div className="card">
          <h2 className="text-2xl md:text-3xl font-extrabold text-blue-900 mb-4 md:mb-6">
            Account Pending Approval
          </h2>
          <p className="mt-4 text-base md:text-lg text-blue-700 font-medium">
            Your registration has been submitted successfully. Your account is
            pending approval from the Chairman or Vice-Chairman.
          </p>
          <p className="mt-2 text-sm md:text-base text-blue-600">
            You will be notified once your account has been approved.
          </p>
        </div>
        <div className="mt-6 md:mt-8">
          <div className="bg-gradient-to-br from-yellow-100 to-yellow-200 border-2 border-yellow-400 rounded-xl p-5 md:p-6">
            <p className="text-base md:text-lg text-yellow-900 font-bold">
              <strong>Status:</strong> Pending Approval
            </p>
          </div>
        </div>
        <div className="mt-6 md:mt-8">
          <Link
            href="/login"
            className="btn-primary w-full inline-block text-center"
          >
            Back to Login
          </Link>
        </div>
      </div>
    </div>
  );
}
