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
  const [currentLoan, setCurrentLoan] = useState<any>(null);
  const [loanModalOpen, setLoanModalOpen] = useState(false);

  useEffect(() => {
    loadStatus();
    loadCycles();
    loadCurrentMonthDeclaration();
    loadCurrentLoan();
  }, []);

  const loadCurrentLoan = async () => {
    try {
      const response = await memberApi.getCurrentLoan();
      if (response.data) setCurrentLoan(response.data);
    } catch {
      // no active loan — leave null
    }
  };

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
                    <div
                      onClick={() => currentLoan && setLoanModalOpen(true)}
                      className={`bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300 ${currentLoan ? 'cursor-pointer hover:ring-2 hover:ring-red-400 hover:shadow-lg transition-all duration-200' : ''}`}
                    >
                      <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                      <p className="text-xl md:text-3xl font-bold text-red-900">
                        K{(currentLoan?.loan_amount ?? status.loan_balance).toLocaleString()}
                      </p>
                      {currentLoan ? (
                        <>
                          <p className="text-xs md:text-sm text-red-700 font-medium mt-1">
                            Outstanding: K{currentLoan.outstanding_balance?.toLocaleString()}
                          </p>
                          <p className="text-xs md:text-sm text-red-500 mt-0.5">
                            Interest paid: K{currentLoan.total_interest_paid?.toLocaleString()}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs md:text-sm text-red-600 mt-1">
                          {status.total_loans_count} {status.total_loans_count === 1 ? 'loan' : 'loans'}
                        </p>
                      )}
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
                <div
                  onClick={() => currentLoan && setLoanModalOpen(true)}
                  className={`bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300 ${currentLoan ? 'cursor-pointer hover:ring-2 hover:ring-red-400 hover:shadow-lg transition-all duration-200' : ''}`}
                >
                  <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                  <p className="text-xl md:text-3xl font-bold text-red-900">
                    K{(currentLoan?.loan_amount ?? status.loan_balance).toLocaleString()}
                  </p>
                  {currentLoan ? (
                    <>
                      <p className="text-xs md:text-sm text-red-700 font-medium mt-1">
                        Outstanding: K{currentLoan.outstanding_balance?.toLocaleString()}
                      </p>
                      <p className="text-xs md:text-sm text-red-500 mt-0.5">
                        Interest paid: K{currentLoan.total_interest_paid?.toLocaleString()}
                      </p>
                    </>
                  ) : (
                    <p className="text-xs md:text-sm text-red-600 mt-1">
                      {status.total_loans_count} {status.total_loans_count === 1 ? 'loan' : 'loans'}
                    </p>
                  )}
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
                <Link
                  href="/dashboard/member/reports"
                  className="block p-5 md:p-6 bg-gradient-to-br from-blue-300 to-blue-400 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-blue-500"
                >
                  <h3 className="font-bold text-lg md:text-xl mb-2">Group Report</h3>
                  <p className="text-sm md:text-base text-blue-100">Monthly group savings, loans & profit summary</p>
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

      {/* Loan Repayment Modal */}
      {loanModalOpen && currentLoan && (() => {
        // Build rows with running balance (oldest first)
        let runningBalance: number = currentLoan.loan_amount ?? 0;
        const rows = [...(currentLoan.repayments ?? [])].map((r: any) => {
          runningBalance = runningBalance - (r.principal ?? 0);
          return { ...r, runningBalance };
        });
        return (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
            onClick={() => setLoanModalOpen(false)}
          >
            <div
              className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="sticky top-0 bg-red-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-start">
                <div>
                  <h2 className="text-xl font-bold">Loan Repayment History</h2>
                  <p className="text-sm text-red-100 mt-0.5">
                    Borrowed: K{currentLoan.loan_amount?.toLocaleString()} &nbsp;·&nbsp;
                    {currentLoan.term_months} {currentLoan.term_months === '1' || currentLoan.term_months === 1 ? 'month' : 'months'} term
                    {currentLoan.interest_rate != null && ` · ${currentLoan.interest_rate}% interest`}
                  </p>
                </div>
                <button
                  onClick={() => setLoanModalOpen(false)}
                  className="text-white hover:text-red-200 text-2xl font-bold leading-none ml-4"
                >×</button>
              </div>

              {/* Summary row */}
              <div className="grid grid-cols-3 gap-3 p-4 bg-red-50 border-b border-red-200">
                <div className="text-center">
                  <p className="text-xs text-red-600 font-medium">Borrowed</p>
                  <p className="text-lg font-bold text-red-900">K{currentLoan.loan_amount?.toLocaleString()}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-red-600 font-medium">Outstanding</p>
                  <p className="text-lg font-bold text-red-700">K{currentLoan.outstanding_balance?.toLocaleString()}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-red-600 font-medium">Interest Paid</p>
                  <p className="text-lg font-bold text-orange-700">K{currentLoan.total_interest_paid?.toLocaleString()}</p>
                </div>
              </div>

              {/* Repayment table */}
              <div className="overflow-y-auto flex-1 p-4">
                {rows.length === 0 ? (
                  <p className="text-center text-gray-500 py-8">No repayments recorded yet.</p>
                ) : (
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr className="bg-red-100 border-b-2 border-red-300">
                        <th className="text-left p-3 font-semibold text-red-900">Date</th>
                        <th className="text-right p-3 font-semibold text-red-900">Principal</th>
                        <th className="text-right p-3 font-semibold text-red-900">Interest</th>
                        <th className="text-right p-3 font-semibold text-red-900">Total Paid</th>
                        <th className="text-right p-3 font-semibold text-red-900">Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Opening balance row */}
                      <tr className="border-b border-gray-200 bg-gray-50">
                        <td className="p-3 text-gray-500 italic" colSpan={4}>Opening balance</td>
                        <td className="p-3 text-right font-semibold text-gray-800">
                          K{currentLoan.loan_amount?.toLocaleString()}
                        </td>
                      </tr>
                      {rows.map((r: any, i: number) => (
                        <tr key={i} className="border-b border-red-100 hover:bg-red-50">
                          <td className="p-3 text-gray-700">
                            {r.date
                              ? new Date(r.date + 'T00:00:00').toLocaleDateString()
                              : 'N/A'}
                          </td>
                          <td className="p-3 text-right text-green-700 font-medium">
                            K{(r.principal ?? 0).toLocaleString()}
                          </td>
                          <td className="p-3 text-right text-orange-600">
                            K{(r.interest ?? 0).toLocaleString()}
                          </td>
                          <td className="p-3 text-right font-semibold text-gray-800">
                            K{(r.total ?? 0).toLocaleString()}
                          </td>
                          <td className="p-3 text-right font-bold text-red-700">
                            K{r.runningBalance.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
