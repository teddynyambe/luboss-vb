'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import Link from 'next/link';

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
    if (!loading && user && !user.approved) {
      router.push('/pending');
    }
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center">
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">
                Village Banking v2
              </h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <span className="text-sm md:text-base text-blue-700 font-medium">
                {user.first_name} {user.last_name}
              </span>
              <button
                onClick={handleLogout}
                className="text-sm md:text-base text-blue-600 hover:text-blue-800 font-semibold px-3 py-2 rounded-lg hover:bg-blue-50"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="card">
          <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4 md:mb-6">
            Welcome to your Dashboard
          </h2>
          <p className="text-base md:text-lg text-blue-700 mb-6 md:mb-8 font-medium">
            Your account has been approved. Select your role dashboard below:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            <Link
              href="/dashboard/member"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Member Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                View statements, make declarations, apply for loans
              </p>
            </Link>

            <Link
              href="/dashboard/admin"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Admin Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                System settings, user management
              </p>
            </Link>

            <Link
              href="/dashboard/chairman"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Chairman Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Approve members, manage cycles, upload constitution
              </p>
            </Link>

            <Link
              href="/dashboard/treasurer"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Treasurer Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Approve deposits, manage penalties, credit ratings
              </p>
            </Link>

            <Link
              href="/dashboard/compliance"
              className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
            >
              <h3 className="text-lg md:text-xl font-bold mb-2">
                Compliance Dashboard
              </h3>
              <p className="text-sm md:text-base text-blue-100">
                Create and manage penalty records
              </p>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
