'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';

interface Member {
  id: string;
  user_id: string;
  status: string;
  created_at?: string;
  activated_at?: string;
  user?: {
    email: string;
    first_name?: string;
    last_name?: string;
  };
}

type FilterStatus = 'pending' | 'active' | 'all';

export default function ChairmanDashboard() {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('pending');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    loadMembers();
  }, [filterStatus]);

  const loadMembers = async () => {
    setLoading(true);
    const endpoint = filterStatus === 'all' 
      ? '/api/chairman/members'
      : `/api/chairman/members?status=${filterStatus}`;
    const response = await api.get<Member[]>(endpoint);
    if (response.data) {
      setMembers(response.data);
    }
    setLoading(false);
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const handleApprove = async (memberId: string) => {
    const response = await api.post(`/api/chairman/members/${memberId}/approve`);
    if (!response.error) {
      showMessage('success', 'Member approved successfully');
      loadMembers();
    } else {
      showMessage('error', response.error || 'Failed to approve member');
    }
  };

  const handleSuspend = async (memberId: string) => {
    const response = await api.post(`/api/chairman/members/${memberId}/suspend`);
    if (!response.error) {
      showMessage('success', 'Member suspended successfully');
      loadMembers();
    } else {
      showMessage('error', response.error || 'Failed to suspend member');
    }
  };

  const handleReactivate = async (memberId: string) => {
    const response = await api.post(`/api/chairman/members/${memberId}/activate`);
    if (!response.error) {
      showMessage('success', 'Member reactivated successfully');
      loadMembers();
    } else {
      showMessage('error', response.error || 'Failed to reactivate member');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Chairman Dashboard</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="space-y-4 md:space-y-6">
          {/* LUBOSS Members */}
          <div className="card">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 md:mb-6 gap-4">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900">LUBOSS Members</h2>
              
              {/* Filter Toggle */}
              <div className="flex gap-2 bg-blue-100 p-1 rounded-lg border-2 border-blue-300">
                <button
                  onClick={() => setFilterStatus('pending')}
                  className={`px-4 py-2 rounded-md font-semibold text-sm md:text-base transition-all ${
                    filterStatus === 'pending'
                      ? 'bg-blue-600 text-white shadow-md'
                      : 'text-blue-700 hover:bg-blue-200'
                  }`}
                >
                  Pending
                </button>
                <button
                  onClick={() => setFilterStatus('active')}
                  className={`px-4 py-2 rounded-md font-semibold text-sm md:text-base transition-all ${
                    filterStatus === 'active'
                      ? 'bg-blue-600 text-white shadow-md'
                      : 'text-blue-700 hover:bg-blue-200'
                  }`}
                >
                  Approved
                </button>
                <button
                  onClick={() => setFilterStatus('all')}
                  className={`px-4 py-2 rounded-md font-semibold text-sm md:text-base transition-all ${
                    filterStatus === 'all'
                      ? 'bg-blue-600 text-white shadow-md'
                      : 'text-blue-700 hover:bg-blue-200'
                  }`}
                >
                  All
                </button>
              </div>
            </div>

            {/* Success/Error Message */}
            {message && (
              <div className={`mb-4 md:mb-6 p-4 rounded-xl border-2 font-medium text-base md:text-lg ${
                message.type === 'success'
                  ? 'bg-green-100 border-green-400 text-green-800'
                  : 'bg-red-100 border-red-400 text-red-800'
              }`}>
                {message.type === 'success' ? '✓ ' : '✗ '}{message.text}
              </div>
            )}
            
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : members.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">
                No {filterStatus === 'all' ? '' : filterStatus} members found
              </p>
            ) : (
              <div className="space-y-3 md:space-y-4">
                {members.map((member) => (
                  <div
                    key={member.id}
                    className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 md:p-5 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl gap-3 md:gap-4"
                  >
                    <div className="flex-1">
                      <p className="font-bold text-base md:text-lg text-blue-900">
                        {member.user?.first_name} {member.user?.last_name}
                      </p>
                      <p className="text-sm md:text-base text-blue-700">{member.user?.email}</p>
                      <p className="text-xs md:text-sm text-blue-600 mt-1">
                        Status: <span className="font-semibold capitalize">{member.status}</span>
                        {member.activated_at && (
                          <span className="ml-2">
                            • Activated: {new Date(member.activated_at).toLocaleDateString()}
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="flex gap-2 w-full sm:w-auto">
                      {member.status === 'pending' && (
                        <button
                          onClick={() => handleApprove(member.id)}
                          className="btn-primary bg-gradient-to-br from-green-500 to-green-600 border-green-600 flex-1 sm:flex-none"
                        >
                          Approve
                        </button>
                      )}
                      {member.status === 'active' && (
                        <button
                          onClick={() => handleSuspend(member.id)}
                          className="btn-primary bg-gradient-to-br from-red-500 to-red-600 border-red-600 flex-1 sm:flex-none"
                        >
                          Suspend
                        </button>
                      )}
                      {member.status === 'suspended' && (
                        <button
                          onClick={() => handleReactivate(member.id)}
                          className="btn-primary bg-gradient-to-br from-green-500 to-green-600 border-green-600 flex-1 sm:flex-none"
                        >
                          Reactivate
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Other Actions */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Actions</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
              <Link
                href="/dashboard/chairman/users"
                className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
              >
                <h3 className="font-bold text-lg md:text-xl mb-2">User Management</h3>
                <p className="text-sm md:text-base text-blue-100">View and update user roles</p>
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
