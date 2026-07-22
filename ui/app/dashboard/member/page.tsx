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
  // Dedicated modal for the Penalties card — richer than the generic
  // transaction history because it shows each penalty's audit narration,
  // status, reversal reason, and reconciliation flag.
  const [penaltyAuditOpen, setPenaltyAuditOpen] = useState(false);
  const [penaltyAuditLoading, setPenaltyAuditLoading] = useState(false);
  const [penaltyAudit, setPenaltyAudit] = useState<{
    summary: {
      total_count: number;
      pending_count: number;
      approved_count: number;
      reversal_pending_count: number;
      reversed_count: number;
      paid_count: number;
      total_owed: number;
    };
    penalties: {
      id: string;
      penalty_type_name: string;
      penalty_type_description?: string | null;
      fee_amount: number;
      status: string;
      date_issued: string | null;
      approved_at?: string | null;
      notes: string | null;
      reversal_reason: string | null;
      reversal_requested_at: string | null;
      reversed_at: string | null;
      is_reconciliation_penalty?: boolean;
    }[];
    ghost_declared_penalties?: {
      effective_month: string;
      declared: number;
      matched_records: number;
      ghost_amount: number;
    }[];
  } | null>(null);
  const [modalType, setModalType] = useState<'savings' | 'penalties' | 'social_fund' | 'admin_fund' | null>(null);
  const [currentLoan, setCurrentLoan] = useState<any>(null);
  const [loanModalOpen, setLoanModalOpen] = useState(false);
  const [creditRating, setCreditRating] = useState<any>(null);

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

  const loadCreditRating = async (cycleId: string) => {
    try {
      const response = await api.get<any>(`/api/member/loans/eligibility/${cycleId}`);
      if (response.data) setCreditRating(response.data);
    } catch {
      setCreditRating(null);
    }
  };

  const openLoanModal = () => {
    if (!currentLoan) return;
    setLoanModalOpen(true);
    const cycleId = currentLoan.cycle_id || cycles[0]?.id;
    if (cycleId && !creditRating) loadCreditRating(cycleId);
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
    if (type === 'penalties') {
      // Open the audit modal instead of the generic transaction history
      // so members see the same rich narration compliance sees.
      openPenaltyAudit();
      return;
    }
    setModalType(type);
    setModalOpen(true);
  };

  const openPenaltyAudit = async () => {
    setPenaltyAuditOpen(true);
    setPenaltyAuditLoading(true);
    setPenaltyAudit(null);
    try {
      const res = await api.get<typeof penaltyAudit>('/api/member/my-penalties');
      if (res.data) setPenaltyAudit(res.data);
    } finally {
      setPenaltyAuditLoading(false);
    }
  };

  const closePenaltyAudit = () => {
    setPenaltyAuditOpen(false);
    setPenaltyAudit(null);
  };

  // Reuse the compliance dashboard's helpers so member-facing timestamps
  // land in browser-local time and narration ISO tokens auto-translate.
  const fmtIso = (iso: string | null | undefined, withTime: boolean) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return withTime
        ? d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
        : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
    } catch {
      return iso;
    }
  };
  const renderNarration = (text: string | null | undefined) => {
    if (!text) return '';
    let out = text.replace(/\b(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})Z\b/g, (m) =>
      fmtIso(m, true)
    );
    out = out.replace(/\b(\d{4}-\d{2}-\d{2})\b(?!T)/g, (m) => fmtIso(m, false));
    return out;
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
                      onClick={openLoanModal}
                      className={`bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300 ${currentLoan ? 'cursor-pointer hover:ring-2 hover:ring-red-400 hover:shadow-lg transition-all duration-200' : ''}`}
                    >
                      <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                      <p className="text-xl md:text-3xl font-bold text-red-900">
                        K{(currentLoan?.loan_amount ?? status.loan_balance).toLocaleString()}
                      </p>
                      {currentLoan ? (
                        <div className="mt-2 space-y-0.5 text-[11px] md:text-xs">
                          <div className="flex justify-between text-red-700">
                            <span>Principal outstanding</span>
                            <span className="font-semibold">
                              K{currentLoan.outstanding_balance?.toLocaleString()}
                            </span>
                          </div>
                          {currentLoan.interest_expected != null && (
                            <div className="flex justify-between text-orange-700">
                              <span>Total interest</span>
                              <span className="font-medium">
                                K{currentLoan.interest_expected.toLocaleString()}
                              </span>
                            </div>
                          )}
                          <div className="flex justify-between text-orange-600">
                            <span>Interest paid</span>
                            <span className="font-medium">
                              K{currentLoan.total_interest_paid?.toLocaleString()}
                            </span>
                          </div>
                          <div className={`flex justify-between ${(currentLoan.interest_outstanding ?? 0) > 0.01 ? 'text-amber-700' : 'text-emerald-700'}`}>
                            <span>Interest owed</span>
                            <span className="font-semibold">
                              K{(currentLoan.interest_outstanding ?? 0).toLocaleString()}
                            </span>
                          </div>
                          <p className="pt-1 mt-1 border-t border-red-300/60 text-[10px] text-red-500 italic">
                            Tap for details
                          </p>
                        </div>
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
                  onClick={openLoanModal}
                  className={`bg-gradient-to-br from-red-100 to-red-200 p-4 md:p-6 rounded-xl border-2 border-red-300 ${currentLoan ? 'cursor-pointer hover:ring-2 hover:ring-red-400 hover:shadow-lg transition-all duration-200' : ''}`}
                >
                  <p className="text-xs md:text-sm text-red-700 font-medium mb-2">Loan Balance</p>
                  <p className="text-xl md:text-3xl font-bold text-red-900">
                    K{(currentLoan?.loan_amount ?? status.loan_balance).toLocaleString()}
                  </p>
                  {currentLoan ? (
                    <div className="mt-2 space-y-0.5 text-[11px] md:text-xs">
                      <div className="flex justify-between text-red-700">
                        <span>Principal outstanding</span>
                        <span className="font-semibold">
                          K{currentLoan.outstanding_balance?.toLocaleString()}
                        </span>
                      </div>
                      {currentLoan.interest_expected != null && (
                        <div className="flex justify-between text-orange-700">
                          <span>Total interest</span>
                          <span className="font-medium">
                            K{currentLoan.interest_expected.toLocaleString()}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between text-orange-600">
                        <span>Interest paid</span>
                        <span className="font-medium">
                          K{currentLoan.total_interest_paid?.toLocaleString()}
                        </span>
                      </div>
                      <div className={`flex justify-between ${(currentLoan.interest_outstanding ?? 0) > 0.01 ? 'text-amber-700' : 'text-emerald-700'}`}>
                        <span>Interest owed</span>
                        <span className="font-semibold">
                          K{(currentLoan.interest_outstanding ?? 0).toLocaleString()}
                        </span>
                      </div>
                      <p className="pt-1 mt-1 border-t border-red-300/60 text-[10px] text-red-500 italic">
                        Tap for details
                      </p>
                    </div>
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
                        <h3 className="font-bold text-lg md:text-xl mb-2">Proof of Payment (PoP)</h3>
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
                <Link
                  href="/dashboard/member/reports/loan-revenue"
                  className="block p-5 md:p-6 bg-gradient-to-br from-emerald-400 to-emerald-500 text-white rounded-xl shadow-lg hover:shadow-xl active:shadow-inner transform active:scale-95 transition-all duration-200 border-2 border-emerald-600"
                >
                  <h3 className="font-bold text-lg md:text-xl mb-2">Loan/Revenue Report</h3>
                  <p className="text-sm md:text-base text-emerald-50">
                    Group-wide loans, interest accrued and collected — same report the treasurer sees
                  </p>
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

      {/* Penalty Audit Modal — member-facing view of their own penalty
          history with the same rich narration compliance sees. Opens
          when the "Penalties" card on the Account Status strip is
          tapped. Times render in the browser's local timezone. */}
      {penaltyAuditOpen && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
          onClick={closePenaltyAudit}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[92vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-yellow-500 text-white px-6 py-4 shrink-0 flex justify-between items-start">
              <div>
                <h2 className="text-xl md:text-2xl font-bold">My Penalties</h2>
                <p className="text-xs text-yellow-50 mt-1">
                  Every penalty on your record — why it was charged and its current status. Times shown in your local timezone.
                </p>
              </div>
              <button
                type="button"
                onClick={closePenaltyAudit}
                className="text-white hover:text-yellow-100 text-2xl leading-none"
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-3">
              {penaltyAuditLoading && (
                <div className="text-center py-10">
                  <div className="animate-spin rounded-full h-10 w-10 border-4 border-yellow-200 border-t-yellow-500 mx-auto"></div>
                  <p className="mt-3 text-yellow-700 text-sm">Loading…</p>
                </div>
              )}
              {!penaltyAuditLoading && penaltyAudit && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                    <div className="p-2 bg-gray-50 border border-gray-200 rounded-lg text-center">
                      <p className="text-[10px] text-gray-600 uppercase">Total</p>
                      <p className="text-base font-bold text-gray-900">{penaltyAudit.summary.total_count}</p>
                    </div>
                    <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-lg text-center">
                      <p className="text-[10px] text-yellow-700 uppercase">Pending</p>
                      <p className="text-base font-bold text-yellow-900">{penaltyAudit.summary.pending_count}</p>
                    </div>
                    <div className="p-2 bg-blue-50 border border-blue-200 rounded-lg text-center">
                      <p className="text-[10px] text-blue-700 uppercase">Approved</p>
                      <p className="text-base font-bold text-blue-900">{penaltyAudit.summary.approved_count}</p>
                    </div>
                    <div className="p-2 bg-orange-50 border border-orange-200 rounded-lg text-center">
                      <p className="text-[10px] text-orange-700 uppercase">Rev. pending</p>
                      <p className="text-base font-bold text-orange-900">{penaltyAudit.summary.reversal_pending_count}</p>
                    </div>
                    <div className="p-2 bg-green-50 border border-green-200 rounded-lg text-center">
                      <p className="text-[10px] text-green-700 uppercase">Paid</p>
                      <p className="text-base font-bold text-green-900">{penaltyAudit.summary.paid_count}</p>
                    </div>
                    <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-center">
                      <p className="text-[10px] text-red-700 uppercase">Reversed</p>
                      <p className="text-base font-bold text-red-900">{penaltyAudit.summary.reversed_count}</p>
                    </div>
                  </div>
                  <p className="text-xs text-yellow-900 bg-yellow-50 border border-yellow-200 rounded px-3 py-2">
                    Total currently on your account (approved + reversal-pending + paid):{' '}
                    <strong>K{penaltyAudit.summary.total_owed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
                  </p>

                  {(penaltyAudit.ghost_declared_penalties?.length ?? 0) > 0 && (
                    <div className="p-3 bg-amber-50 border-2 border-amber-300 rounded-lg">
                      <p className="text-xs font-bold text-amber-900 mb-1">⚠ Unexplained declared penalties</p>
                      <p className="text-[11px] text-amber-800 mb-2">
                        You paid these penalty amounts on your declaration, but the system doesn&apos;t have a
                        record explaining <em>why</em> for those months. The money went through — it credited
                        the group&apos;s penalties account — but there&apos;s no specific charge attached.
                        Ask the treasurer or compliance officer to clarify or reverse if it was declared in error.
                      </p>
                      <div className="space-y-1">
                        {penaltyAudit.ghost_declared_penalties!.map((g) => {
                          const mLabel = new Date(g.effective_month + 'T00:00:00').toLocaleDateString(
                            undefined,
                            { year: 'numeric', month: 'long' },
                          );
                          return (
                            <div key={g.effective_month} className="text-[11px] text-amber-900 flex justify-between">
                              <span><strong>{mLabel}</strong></span>
                              <span>
                                Declared K{g.declared.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                {' · matched K'}{g.matched_records.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                {' · '}
                                <strong>unmatched K{g.ghost_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {penaltyAudit.penalties.length === 0 ? (
                    <p className="text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-3">
                      No penalties on your record.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {penaltyAudit.penalties.map((p) => {
                        const statusStyle = (() => {
                          switch (p.status) {
                            case 'approved':          return 'bg-blue-100 text-blue-800 border-blue-300';
                            case 'reversal_pending':  return 'bg-orange-100 text-orange-800 border-orange-300';
                            case 'reversed':          return 'bg-red-100 text-red-800 border-red-300';
                            case 'paid':              return 'bg-green-100 text-green-800 border-green-300';
                            case 'pending':           return 'bg-yellow-100 text-yellow-800 border-yellow-300';
                            default:                  return 'bg-gray-100 text-gray-800 border-gray-300';
                          }
                        })();
                        return (
                          <div
                            key={p.id}
                            className={`bg-white border-2 rounded-lg p-3 ${
                              p.is_reconciliation_penalty && p.status !== 'reversed'
                                ? 'border-amber-300 ring-2 ring-amber-100'
                                : 'border-yellow-100'
                            }`}
                          >
                            <div className="flex flex-wrap justify-between items-start gap-2 mb-2">
                              <div>
                                <h3 className="font-bold text-yellow-900">{p.penalty_type_name}</h3>
                                <p className="text-xs text-yellow-700">
                                  K{p.fee_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  {' · issued '}{fmtIso(p.date_issued, true)}
                                </p>
                              </div>
                              <div className="flex flex-wrap items-center gap-1">
                                {p.is_reconciliation_penalty && p.status !== 'reversed' && (
                                  <span
                                    className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide rounded border bg-amber-100 text-amber-900 border-amber-300"
                                    title="This penalty was charged on a treasurer-reconciliation entry — compliance may reverse it."
                                  >
                                    Reconciliation
                                  </span>
                                )}
                                <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${statusStyle}`}>
                                  {p.status.replace(/_/g, ' ')}
                                </span>
                              </div>
                            </div>
                            {p.notes && (
                              <p className="mt-1 text-sm text-yellow-900 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 whitespace-pre-wrap">
                                {renderNarration(p.notes)}
                              </p>
                            )}
                            {(p.approved_at || p.reversal_requested_at || p.reversed_at || p.reversal_reason) && (
                              <div className="mt-2 text-[11px] text-yellow-800 space-y-0.5">
                                {p.approved_at && (
                                  <div>Approved at <strong>{fmtIso(p.approved_at, true)}</strong>.</div>
                                )}
                                {p.reversal_requested_at && (
                                  <div>Reversal requested at <strong>{fmtIso(p.reversal_requested_at, true)}</strong>.</div>
                                )}
                                {p.reversal_reason && (
                                  <div>Reversal reason: <em>{p.reversal_reason}</em></div>
                                )}
                                {p.reversed_at && (
                                  <div>Reversed at <strong>{fmtIso(p.reversed_at, true)}</strong>.</div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
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
                  <p className="text-xs text-red-200 mt-0.5">
                    {currentLoan.disbursement_date && (
                      <>Date Borrowed: {new Date(currentLoan.disbursement_date + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</>
                    )}
                    {currentLoan.disbursement_date && currentLoan.maturity_date && ' · '}
                    {currentLoan.maturity_date && (
                      <>Maturity: {new Date(currentLoan.maturity_date + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</>
                    )}
                  </p>
                </div>
                <button
                  onClick={() => setLoanModalOpen(false)}
                  className="text-white hover:text-red-200 text-2xl font-bold leading-none ml-4"
                >×</button>
              </div>

              {/* Summary row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-red-50 border-b border-red-200">
                <div className="text-center">
                  <p className="text-xs text-red-600 font-medium">Borrowed</p>
                  <p className="text-lg font-bold text-red-900">K{currentLoan.loan_amount?.toLocaleString()}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-red-600 font-medium">Outstanding</p>
                  <p className="text-lg font-bold text-red-700">K{currentLoan.outstanding_balance?.toLocaleString()}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-orange-600 font-medium">Interest Paid</p>
                  <p className="text-lg font-bold text-orange-700">K{currentLoan.total_interest_paid?.toLocaleString()}</p>
                  {currentLoan.interest_expected != null && (
                    <p className="text-[10px] text-orange-500 mt-0.5">
                      of K{currentLoan.interest_expected.toLocaleString()} accrued
                    </p>
                  )}
                </div>
                <div className="text-center">
                  <p className="text-xs text-amber-600 font-medium">Interest Owed</p>
                  <p className={`text-lg font-bold ${(currentLoan.interest_outstanding ?? 0) > 0.01 ? 'text-amber-700' : 'text-emerald-700'}`}>
                    K{(currentLoan.interest_outstanding ?? 0).toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Credit rating summary */}
              {creditRating?.has_credit_rating && (
                <div className="px-4 py-3 bg-blue-50 border-b border-blue-200">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div>
                      <p className="text-[11px] uppercase tracking-wider text-blue-600 font-semibold">Credit Rating</p>
                      <p className="text-base font-bold text-blue-900">{creditRating.tier_name}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[11px] text-blue-600 font-medium">Borrowing limit</p>
                      <p className="text-sm font-bold text-blue-900">
                        K{creditRating.max_loan_amount?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                      <p className="text-[10px] text-blue-500">
                        {creditRating.multiplier}× savings (K{creditRating.savings_balance?.toLocaleString(undefined, { maximumFractionDigits: 0 })})
                      </p>
                    </div>
                  </div>
                  {Array.isArray(creditRating.available_terms) && creditRating.available_terms.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {creditRating.available_terms.map((t: any, i: number) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-blue-300 text-[11px] text-blue-800"
                        >
                          <span className="font-semibold">{t.term_label}</span>
                          <span className="text-blue-500">·</span>
                          <span>{t.interest_rate}% interest</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

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
