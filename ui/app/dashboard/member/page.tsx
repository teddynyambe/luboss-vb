'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { memberApi } from '@/lib/memberApi';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';
import TransactionHistoryModal from '@/components/TransactionHistoryModal';

interface AccountStatus {
  member_id: string;
  savings_balance: number;
  loan_balance: number;
  social_fund_balance: number;
  social_fund_required?: number | null;
  admin_fund_balance: number;
  admin_fund_required?: number | null;
  penalties_balance: number;
  total_loans_count: number;
  pending_penalties_count: number;
}

interface Cycle {
  id: string;
  year: number;
  cycle_number: number;
  start_date: string;
  end_date?: string;
  status: string;
}

export default function MemberDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<AccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [cyclesLoading, setCyclesLoading] = useState(true);
  const [hasActiveCycles, setHasActiveCycles] = useState(true);
  const [hasCurrentMonthDeclaration, setHasCurrentMonthDeclaration] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<'savings' | 'penalties' | 'social_fund' | 'admin_fund' | null>(null);

  useEffect(() => {
    loadStatus();
    loadCycles();
    loadCurrentMonthDeclaration();
  }, []);

  const loadStatus = async () => {
    const response = await api.get<AccountStatus>('/api/member/status');
    if (response.data) {
      setStatus(response.data);
    }
    setLoading(false);
  };

  const loadCycles = async () => {
    setCyclesLoading(true);
    try {
      const response = await api.get<Cycle[]>('/api/member/cycles');
      console.log('Cycles API response:', response);
      if (response.data && Array.isArray(response.data) && response.data.length > 0) {
        console.log('Found active cycles:', response.data);
        setCycles(response.data);
        setHasActiveCycles(true);
      } else {
        console.log('No active cycles found. Response:', response);
        setHasActiveCycles(false);
      }
    } catch (error) {
      console.error('Error loading cycles:', error);
      setHasActiveCycles(false);
    } finally {
      setCyclesLoading(false);
    }
  };

  const loadCurrentMonthDeclaration = async () => {
    try {
      const response = await memberApi.getCurrentMonthDeclaration();
      setHasCurrentMonthDeclaration(response.data !== null);
    } catch (error) {
      console.error('Error loading current month declaration:', error);
      setHasCurrentMonthDeclaration(false);
    }
  };

  const handleCardClick = (type: 'savings' | 'penalties' | 'social_fund' | 'admin_fund') => {
    setModalType(type);
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setModalType(null);
  };

  const getModalTitle = (type: 'savings' | 'penalties' | 'social_fund' | 'admin_fund' | null): string => {
    switch (type) {
      case 'savings':
        return 'Savings to Date - Transaction History';
      case 'penalties':
        return 'Penalties - Transaction History';
      case 'social_fund':
        return 'Social Fund - Transaction History';
      case 'admin_fund':
        return 'Admin Fund - Transaction History';
      default:
        return 'Transaction History';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Member Dashboard</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        {loading || cyclesLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
            <p className="mt-4 text-blue-700 text-lg">Loading...</p>
          </div>
        ) : !hasActiveCycles ? (
          <div className="card">
            <div className="text-center py-12">
              <div className="mb-6">
                <svg className="mx-auto h-24 w-24 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4">No Active Cycles Available</h2>
              <p className="text-lg md:text-xl text-blue-700 mb-6">
                There are currently no active cycles. Please contact the administrator to activate a cycle.
              </p>
              {status && (
                <div className="mt-8 pt-8 border-t-2 border-blue-200">
                  <h3 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Account Status</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
                    <div
                      onClick={() => handleCardClick('savings')}
                      className="bg-gradient-to-br from-blue-100 to-blue-200 p-4 md:p-6 rounded-xl border-2 border-blue-300 cursor-pointer hover:ring-2 hover:ring-blue-400 hover:shadow-lg transition-all duration-200"
                    >
                      <p className="text-xs md:text-sm text-blue-700 font-medium mb-2">Savings to Date</p>
                      <p className="text-xl md:text-3xl font-bold text-blue-900">
                        K{status.savings_balance.toLocaleString()}
                      </p>
                    </div>
                    <div className="bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300">
                      <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                      <p className="text-xl md:text-3xl font-bold text-red-900">
                        K{status.loan_balance.toLocaleString()}
                      </p>
                      <p className="text-xs md:text-sm text-red-600 mt-1">
                        {status.total_loans_count} {status.total_loans_count === 1 ? 'loan' : 'loans'}
                      </p>
                    </div>
                    <div
                      onClick={() => handleCardClick('social_fund')}
                      className="bg-gradient-to-br from-purple-100 to-purple-200 p-4 md:p-6 rounded-xl border-2 border-purple-300 cursor-pointer hover:ring-2 hover:ring-purple-400 hover:shadow-lg transition-all duration-200"
                    >
                      <p className="text-xs md:text-sm text-purple-700 font-medium mb-2">Social Fund</p>
                      <p className="text-xl md:text-3xl font-bold text-purple-900">
                        K{status.social_fund_balance.toLocaleString()}
                      </p>
                    </div>
                    <div
                      onClick={() => handleCardClick('admin_fund')}
                      className="bg-gradient-to-br from-indigo-100 to-indigo-200 p-4 md:p-6 rounded-xl border-2 border-indigo-300 cursor-pointer hover:ring-2 hover:ring-indigo-400 hover:shadow-lg transition-all duration-200"
                    >
                      <p className="text-xs md:text-sm text-indigo-700 font-medium mb-2">Admin Fund</p>
                      <p className="text-xl md:text-3xl font-bold text-indigo-900">
                        K{status.admin_fund_balance.toLocaleString()}
                      </p>
                    </div>
                    <div
                      onClick={() => handleCardClick('penalties')}
                      className="bg-gradient-to-br from-yellow-100 to-yellow-200 p-4 md:p-6 rounded-xl border-2 border-yellow-300 cursor-pointer hover:ring-2 hover:ring-yellow-400 hover:shadow-lg transition-all duration-200"
                    >
                      <p className="text-xs md:text-sm text-yellow-700 font-medium mb-2">Penalties</p>
                      <p className="text-xl md:text-3xl font-bold text-yellow-900">
                        K{status.penalties_balance.toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : status ? (
          <div className="space-y-4 md:space-y-6">
            {/* Account Status Card */}
            <div className="card">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Account Status</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
                <div
                  onClick={() => handleCardClick('savings')}
                  className="bg-gradient-to-br from-blue-100 to-blue-200 p-4 md:p-6 rounded-xl border-2 border-blue-300 cursor-pointer hover:ring-2 hover:ring-blue-400 hover:shadow-lg transition-all duration-200"
                >
                  <p className="text-xs md:text-sm text-blue-700 font-medium mb-2">Savings to Date</p>
                  <p className="text-xl md:text-3xl font-bold text-blue-900">
                    K{status.savings_balance.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300">
                  <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                  <p className="text-xl md:text-3xl font-bold text-red-900">
                    K{status.loan_balance.toLocaleString()}
                  </p>
                  <p className="text-xs md:text-sm text-red-600 mt-1">
                    {status.total_loans_count} {status.total_loans_count === 1 ? 'loan' : 'loans'}
                  </p>
                </div>
                <div
                  onClick={() => handleCardClick('social_fund')}
                  className="bg-gradient-to-br from-purple-100 to-purple-200 p-4 md:p-6 rounded-xl border-2 border-purple-300 cursor-pointer hover:ring-2 hover:ring-purple-400 hover:shadow-lg transition-all duration-200"
                >
                  <p className="text-xs md:text-sm text-purple-700 font-medium mb-2">Social Fund</p>
                  <p className="text-xl md:text-3xl font-bold text-purple-900">
                    K{status.social_fund_balance.toLocaleString()}
                  </p>
                  {status.social_fund_required !== null && status.social_fund_required !== undefined && (
                    <p className="text-xs md:text-sm text-purple-600 mt-1">
                      of K{status.social_fund_required.toLocaleString()} required
                    </p>
                  )}
                </div>
                <div
                  onClick={() => handleCardClick('admin_fund')}
                  className="bg-gradient-to-br from-indigo-100 to-indigo-200 p-4 md:p-6 rounded-xl border-2 border-indigo-300 cursor-pointer hover:ring-2 hover:ring-indigo-400 hover:shadow-lg transition-all duration-200"
                >
                  <p className="text-xs md:text-sm text-indigo-700 font-medium mb-2">Admin Fund</p>
                  <p className="text-xl md:text-3xl font-bold text-indigo-900">
                    K{status.admin_fund_balance.toLocaleString()}
                  </p>
                  {status.admin_fund_required !== null && status.admin_fund_required !== undefined && (
                    <p className="text-xs md:text-sm text-indigo-600 mt-1">
                      of K{status.admin_fund_required.toLocaleString()} required
                    </p>
                  )}
                </div>
                <div
                  onClick={() => handleCardClick('penalties')}
                  className="bg-gradient-to-br from-yellow-100 to-yellow-200 p-4 md:p-6 rounded-xl border-2 border-yellow-300 cursor-pointer hover:ring-2 hover:ring-yellow-400 hover:shadow-lg transition-all duration-200"
                >
                  <p className="text-xs md:text-sm text-yellow-700 font-medium mb-2">Penalties</p>
                  <p className="text-xl md:text-3xl font-bold text-yellow-900">
                    K{status.penalties_balance.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="card">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Quick Actions</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
                      <Link
                        href="/dashboard/member/declarations"
                        className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
                      >
                        <h3 className="font-bold text-lg md:text-xl mb-2">Monthly Declarations</h3>
                        <p className="text-sm md:text-base text-blue-100">
                          Declare savings and contributions, View and Manage declarations for the current month
                        </p>
                      </Link>
                <Link
                  href="/dashboard/member/loans"
                  className="block p-5 md:p-6 bg-gradient-to-br from-blue-400 to-blue-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-600"
                >
                  <h3 className="font-bold text-lg md:text-xl mb-2">Loan Management</h3>
                  <p className="text-sm md:text-base text-blue-100">Submit, view and edit loan applications</p>
                </Link>
                      <Link
                        href="/dashboard/member/payment-proof"
                        className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
                      >
                        <h3 className="font-bold text-lg md:text-xl mb-2">Payment Proof</h3>
                        <p className="text-sm md:text-base text-blue-100">Upload and view deposit proofs</p>
                      </Link>
                <Link
                  href="/dashboard/member/statement"
                  className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
                >
                  <h3 className="font-bold text-lg md:text-xl mb-2">View Statement</h3>
                  <p className="text-sm md:text-base text-blue-100">View account statement</p>
                </Link>
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <p className="text-blue-700 text-lg">Unable to load account status.</p>
          </div>
        )}
      </main>

      {/* Transaction History Modal */}
      {modalType && (
        <TransactionHistoryModal
          open={modalOpen}
          onClose={handleCloseModal}
          type={modalType}
          title={getModalTitle(modalType)}
        />
      )}
    </div>
  );
}
