'use client';

import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import UserMenu from '@/components/UserMenu';

export default function ChairmanDashboard() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Chairman Dashboard</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="space-y-4 md:space-y-6">
          {/* Actions */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Actions</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
              <Link
                href="/dashboard/chairman/users"
                className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
              >
                <h3 className="font-bold text-lg md:text-xl mb-2">User Management</h3>
                <p className="text-sm md:text-base text-blue-100">Manage users, roles, and member approvals</p>
              </Link>
              <Link
                href="/dashboard/chairman/upload-constitution"
                className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
              >
                <h3 className="font-bold text-lg md:text-xl mb-2">Upload Constitution</h3>
                <p className="text-sm md:text-base text-blue-100">Upload or update constitution document</p>
              </Link>
              <Link
                href="/dashboard/chairman/cycles"
                className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
              >
                <h3 className="font-bold text-lg md:text-xl mb-2">Manage Cycles</h3>
                <p className="text-sm md:text-base text-blue-100">Configure cycle phases and dates</p>
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
