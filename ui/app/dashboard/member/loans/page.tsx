'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { memberApi, LoanApplicationCreate } from '@/lib/memberApi';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface Cycle {
  id: string;
  year: number;
  cycle_number: number;
  start_date: string;
  end_date?: string;
}

/** Parse a date-only string (YYYY-MM-DD) as local midnight to avoid UTC timezone shift. */
function parseLocalDate(dateStr: string): Date {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export default function LoanApplicationPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [selectedCycle, setSelectedCycle] = useState<string>('');
  const [formData, setFormData] = useState<LoanApplicationCreate>({
    cycle_id: '',
    amount: 0,
    term_months: '1',
    notes: '',
  });
  const [editingApplication, setEditingApplication] = useState<string | null>(null);
  const [editingData, setEditingData] = useState<LoanApplicationCreate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [myLoans, setMyLoans] = useState<any[]>([]);
  const [loadingLoans, setLoadingLoans] = useState(false);
  const [loanEligibility, setLoanEligibility] = useState<any>(null);
  const [loadingEligibility, setLoadingEligibility] = useState(false);
  const [currentLoan, setCurrentLoan] = useState<any>(null);
  const [loadingCurrentLoan, setLoadingCurrentLoan] = useState(false);
  const [withdrawing, setWithdrawing] = useState<string | null>(null);
  const [showFormModal, setShowFormModal] = useState(false);
  const [lastSuccessType, setLastSuccessType] = useState<'create' | 'update' | null>(null);

  useEffect(() => {
    loadCycles();
    loadMyLoans();
    loadCurrentLoan();
  }, []);

  const loadCycles = async () => {
    try {
      // Get active cycles from member API
      const response = await api.get<Cycle[]>('/api/member/cycles');
      if (response.data && response.data.length > 0) {
        setCycles(response.data);
        // Automatically set to the first (current) active cycle
        const currentCycle = response.data[0];
        setSelectedCycle(currentCycle.id);
        setFormData({ ...formData, cycle_id: currentCycle.id });
        // Load eligibility for the current cycle
        loadLoanEligibility(currentCycle.id, false);
      } else {
        setError('No active cycles available. Please contact the administrator.');
      }
    } catch (err) {
      console.error('Error loading cycles:', err);
      setError('Unable to load cycles. Please try again later.');
    }
  };

  const loadMyLoans = async () => {
    setLoadingLoans(true);
    try {
      const response = await memberApi.getLoans();
      if (response.data) {
        setMyLoans(response.data);
      }
    } catch (err) {
      console.error('Error loading loans:', err);
    } finally {
      setLoadingLoans(false);
    }
  };

  const loadCurrentLoan = async () => {
    setLoadingCurrentLoan(true);
    try {
      const response = await memberApi.getCurrentLoan();
      if (response.data) {
        setCurrentLoan(response.data);
      } else {
        setCurrentLoan(null);
      }
    } catch (err) {
      console.error('Error loading current loan:', err);
      setCurrentLoan(null);
    } finally {
      setLoadingCurrentLoan(false);
    }
  };

  const handleWithdraw = async (applicationId: string) => {
    if (!confirm('Are you sure you want to withdraw this loan application?')) {
      return;
    }

    setWithdrawing(applicationId);
    try {
      const response = await memberApi.withdrawLoanApplication(applicationId);
      if (!response.error) {
        setSuccess(true);
        setError('');
        await loadMyLoans();
        setTimeout(() => setSuccess(false), 3000);
      } else {
        setError(response.error || 'Failed to withdraw loan application');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to withdraw loan application');
    } finally {
      setWithdrawing(null);
    }
  };

  const loadLoanEligibility = async (cycleId: string, preserveFormData: boolean = false) => {
    if (!cycleId) return;
    setLoadingEligibility(true);
    try {
      const response = await api.get(`/api/member/loans/eligibility/${cycleId}`);
      if (response.data) {
        setLoanEligibility(response.data);
        // If available terms exist, set the first one as default (only if not preserving form data)
        const eligibilityData = response.data as { available_terms?: Array<{ term_months?: number }> };
        if (!preserveFormData && eligibilityData.available_terms && eligibilityData.available_terms.length > 0) {
          const firstTerm = eligibilityData.available_terms[0];
          if (firstTerm.term_months) {
            setFormData(prev => ({ ...prev, term_months: String(firstTerm.term_months) }));
          }
        }
      } else {
        setLoanEligibility(null);
      }
    } catch (err) {
      console.error('Error loading loan eligibility:', err);
      setLoanEligibility(null);
    } finally {
      setLoadingEligibility(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    // Cycle is read-only, so we don't handle cycle_id changes
    if (name === 'amount') {
      const amount = parseFloat(value) || 0;
      setFormData({ ...formData, amount });
      // Validate against max loan amount
      if (loanEligibility && loanEligibility.max_loan_amount && amount > loanEligibility.max_loan_amount) {
        setError(`Loan amount cannot exceed maximum allowed: K${loanEligibility.max_loan_amount.toLocaleString()}`);
      } else if (error && error.includes('cannot exceed')) {
        setError('');
      }
    } else {
      setFormData({ ...formData, [name]: value });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setLoading(true);

    if (!selectedCycle || formData.amount <= 0) {
      setError('Please select a cycle and enter a valid loan amount');
      setLoading(false);
      return;
    }

    // If editing, verify the loan is still pending
    if (editingApplication) {
      // Check if the loan is still pending by finding it in myLoans
      const loanToEdit = myLoans.find(loan => loan.id === editingApplication);
      if (!loanToEdit || loanToEdit.status !== 'pending') {
        setError('This loan application can no longer be edited. It may have been approved or its status has changed.');
        setLoading(false);
        closeFormModal();
        await loadMyLoans();
        return;
      }
    }

    const loanData: LoanApplicationCreate = {
      cycle_id: selectedCycle,
      amount: formData.amount,
      term_months: formData.term_months,
      notes: formData.notes || undefined,
    };

    try {
      let response;
      if (editingApplication) {
        response = await memberApi.updateLoanApplication(editingApplication, loanData);
        if (response.data) {
          setLastSuccessType('update');
          setSuccess(true);
          closeFormModal();
          await loadMyLoans();
          await loadCurrentLoan();
          setTimeout(() => { setSuccess(false); setLastSuccessType(null); }, 3000);
        } else {
          setError(response.error || 'Failed to update loan application');
        }
      } else {
        response = await memberApi.applyForLoan(loanData);
        if (response.data) {
          setLastSuccessType('create');
          setSuccess(true);
          closeFormModal();
          await loadMyLoans();
          await loadCurrentLoan();
          setTimeout(() => { setSuccess(false); setLastSuccessType(null); }, 3000);
        } else {
          setError(response.error || 'Failed to submit loan application');
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to submit loan application');
    } finally {
      setLoading(false);
    }
  };

  const openApplyModal = () => {
    setEditingApplication(null);
    setEditingData(null);
    setError('');
    setFormData({
      cycle_id: selectedCycle,
      amount: 0,
      term_months: formData.term_months || '1',
      notes: '',
    });
    if (selectedCycle) loadLoanEligibility(selectedCycle, false);
    setShowFormModal(true);
  };

  const handleEdit = (application: any) => {
    // Only allow editing pending applications
    if (application.status !== 'pending') {
      setError('Only pending loan applications can be edited.');
      return;
    }

    // Ensure amount is a number, not a string or undefined
    const amountValue = application.amount 
      ? (typeof application.amount === 'string' ? parseFloat(application.amount) : Number(application.amount))
      : 0;
    
    // Validate that we got a valid number (not NaN)
    const finalAmount = (isNaN(amountValue) || amountValue < 0) ? 0 : amountValue;

    setEditingApplication(application.id);
    setSelectedCycle(application.cycle_id);
    setEditingData({
      cycle_id: application.cycle_id,
      amount: finalAmount,
      term_months: application.term_months,
      notes: application.notes || '',
    });
    
    // Set form data with the amount value
    setFormData({
      cycle_id: application.cycle_id,
      amount: finalAmount,
      term_months: application.term_months || '1',
      notes: application.notes || '',
    });
    
    setError('');
    
    // Load eligibility but preserve the form data we just set
    if (application.cycle_id) {
      loadLoanEligibility(application.cycle_id, true);
    }
    
    setShowFormModal(true);
  };

  const closeFormModal = () => {
    setShowFormModal(false);
    setEditingApplication(null);
    setEditingData(null);
    setFormData({ cycle_id: selectedCycle, amount: 0, term_months: formData.term_months || '1', notes: '' });
    setError('');
  };

  const handleCancelEdit = () => {
    closeFormModal();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Loan Management</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="space-y-4 md:space-y-6">
          {success && (
            <div className="bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
              ✓ Loan application {lastSuccessType === 'update' ? 'updated' : 'submitted'} successfully!
            </div>
          )}

          {/* Current Active Loan */}
          {loadingCurrentLoan ? (
            <div className="card">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Current Loan</h2>
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-12 w-12 md:h-16 md:w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            </div>
          ) : currentLoan ? (
            <div className="card">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Current Active Loan</h2>
              <div className="space-y-4 md:space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <p className="text-sm md:text-base text-blue-700 font-medium mb-1">Loan Amount</p>
                    <p className="text-xl md:text-2xl font-bold text-blue-900">
                      K{currentLoan.loan_amount?.toLocaleString() || '0.00'}
                    </p>
                  </div>
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <p className="text-sm md:text-base text-blue-700 font-medium mb-1">Outstanding Balance</p>
                    <p className="text-xl md:text-2xl font-bold text-blue-900">
                      K{currentLoan.outstanding_balance?.toLocaleString() || '0.00'}
                    </p>
                  </div>
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <p className="text-sm md:text-base text-blue-700 font-medium mb-1">Total Principal Paid</p>
                    <p className="text-xl md:text-2xl font-bold text-green-700">
                      K{currentLoan.total_principal_paid?.toLocaleString() || '0.00'}
                    </p>
                  </div>
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <p className="text-sm md:text-base text-blue-700 font-medium mb-1">Total Interest Paid</p>
                    <p className="text-xl md:text-2xl font-bold text-green-700">
                      K{currentLoan.total_interest_paid?.toLocaleString() || '0.00'}
                    </p>
                  </div>
                </div>
                
                {currentLoan.repayments && currentLoan.repayments.length > 0 && (() => {
                  let runningBal: number = currentLoan.loan_amount ?? 0;
                  const rows = [...currentLoan.repayments].map((r: any) => {
                    runningBal = runningBal - (r.principal ?? 0);
                    return { ...r, runningBal };
                  });
                  return (
                    <div>
                      <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-3">Repayment History</h3>
                      <div className="overflow-x-auto">
                        <table className="w-full border-collapse">
                          <thead>
                            <tr className="bg-blue-100 border-b-2 border-blue-300">
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Date</th>
                              <th className="text-right p-3 text-sm md:text-base font-semibold text-blue-900">Principal</th>
                              <th className="text-right p-3 text-sm md:text-base font-semibold text-blue-900">Interest</th>
                              <th className="text-right p-3 text-sm md:text-base font-semibold text-blue-900">Total</th>
                              <th className="text-right p-3 text-sm md:text-base font-semibold text-blue-900">Balance</th>
                            </tr>
                          </thead>
                          <tbody>
                            {/* Opening balance */}
                            <tr className="border-b border-blue-200 bg-blue-50">
                              <td className="p-3 text-sm text-blue-500 italic" colSpan={4}>Opening balance</td>
                              <td className="p-3 text-right text-sm font-semibold text-blue-900">
                                K{(currentLoan.loan_amount ?? 0).toLocaleString()}
                              </td>
                            </tr>
                            {rows.map((repayment: any, index: number) => (
                              <tr key={index} className="border-b border-blue-200">
                                <td className="p-3 text-sm md:text-base text-blue-800">
                                  {repayment.date ? parseLocalDate(repayment.date).toLocaleDateString() : 'N/A'}
                                </td>
                                <td className="p-3 text-sm md:text-base text-right text-green-700 font-medium">
                                  K{(repayment.principal ?? 0).toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base text-right text-orange-600">
                                  K{(repayment.interest ?? 0).toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base text-right font-semibold text-blue-900">
                                  K{(repayment.total ?? 0).toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base text-right font-bold text-red-700">
                                  K{repayment.runningBal.toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
          ) : null}

          {/* My Loans */}
          <div className="card">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-4 md:mb-6">
              <h2 className="text-xl md:text-2xl font-bold text-blue-900">My Loans</h2>
              <button
                type="button"
                onClick={openApplyModal}
                disabled={!selectedCycle || cycles.length === 0}
                className="px-4 py-2 md:px-6 md:py-3 bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-600 text-white rounded-xl hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold transition-all duration-200 shadow-lg hover:shadow-xl"
              >
                Apply for Loan
              </button>
            </div>
            {loadingLoans ? (
              <div className="text-center py-8 md:py-12">
                <div className="animate-spin rounded-full h-12 w-12 md:h-16 md:w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : myLoans.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">
                No loans yet. Click <strong>Apply for Loan</strong> above to get started.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <div className="space-y-3 md:space-y-4">
                  {myLoans.map((loan) => (
                    <div
                      key={loan.id}
                      className="bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl p-4 md:p-6"
                    >
                      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 flex-1">
                          <div>
                            <p className="text-xs md:text-sm text-blue-700 font-medium mb-1">Amount</p>
                            <p className="text-base md:text-lg font-bold text-blue-900">
                              K{loan.amount.toLocaleString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700 font-medium mb-1">Term</p>
                            <p className="text-base md:text-lg font-semibold text-blue-900">
                              {loan.term_months} {loan.term_months === '1' ? 'Month' : 'Months'}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700 font-medium mb-1">Status</p>
                            <span
                              className={`inline-block px-3 py-1 md:px-4 md:py-2 text-xs md:text-sm font-bold rounded-full ${
                                loan.status === 'approved' || loan.status === 'disbursed' || loan.status === 'active' || loan.status === 'open'
                                  ? 'bg-green-200 text-green-900'
                                  : loan.status === 'closed'
                                  ? 'bg-blue-200 text-blue-900'
                                  : loan.status === 'rejected' || loan.status === 'withdrawn'
                                  ? 'bg-red-200 text-red-900'
                                  : 'bg-yellow-200 text-yellow-900'
                              }`}
                            >
                              {loan.status === 'closed' 
                                ? 'Paid Off' 
                                : loan.status === 'open' || loan.status === 'active'
                                ? 'Active'
                                : loan.status.charAt(0).toUpperCase() + loan.status.slice(1)}
                            </span>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700 font-medium mb-1">Date</p>
                            <p className="text-base md:text-lg font-semibold text-blue-900">
                              {loan.application_date ? parseLocalDate(loan.application_date).toLocaleDateString() : 'N/A'}
                            </p>
                          </div>
                        </div>
                        {loan.type === 'application' && loan.status === 'pending' && (
                          <div className="flex gap-2 md:gap-3">
                            <button
                              onClick={() => handleEdit(loan)}
                              className="px-4 py-2 bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-600 text-white rounded-xl hover:from-blue-600 hover:to-blue-700 text-sm md:text-base font-semibold transition-all duration-200"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleWithdraw(loan.id)}
                              disabled={withdrawing === loan.id}
                              className="px-4 py-2 bg-gradient-to-br from-red-500 to-red-600 border-2 border-red-600 text-white rounded-xl hover:from-red-600 hover:to-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold transition-all duration-200"
                            >
                              {withdrawing === loan.id ? 'Withdrawing...' : 'Withdraw'}
                            </button>
                          </div>
                        )}
                      </div>
                      {loan.notes && (
                        <div className="mt-3 pt-3 border-t border-blue-300">
                          <p className="text-xs md:text-sm text-blue-700 font-medium mb-1">Notes:</p>
                          <p className="text-sm md:text-base text-blue-900">{loan.notes}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Application / Edit Form Modal */}
      {showFormModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={closeFormModal}>
          <div
            className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">
                {editingApplication ? 'Edit Loan Application' : 'Apply for Loan'}
              </h2>
              <button
                type="button"
                onClick={closeFormModal}
                className="text-white hover:text-blue-200 text-2xl font-bold leading-none"
              >
                ×
              </button>
            </div>

            <div className="p-6 md:p-8">
              {error && (
                <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4 md:space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                  <div>
                    <label htmlFor="modal_cycle_id" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Cycle *
                    </label>
                    {selectedCycle && cycles.length > 0 ? (
                      <input
                        type="text"
                        id="modal_cycle_id"
                        name="cycle_id"
                        value={cycles.find(c => c.id === selectedCycle) 
                          ? `${cycles.find(c => c.id === selectedCycle)!.year} - Cycle ${cycles.find(c => c.id === selectedCycle)!.cycle_number}`
                          : 'Loading...'}
                        readOnly
                        className="w-full bg-gray-100 border-2 border-gray-300 rounded-xl px-4 py-2 text-blue-900 cursor-not-allowed"
                      />
                    ) : (
                      <input
                        type="text"
                        id="modal_cycle_id"
                        name="cycle_id"
                        value="No active cycle available"
                        readOnly
                        className="w-full bg-gray-100 border-2 border-gray-300 rounded-xl px-4 py-2 text-gray-500 cursor-not-allowed"
                      />
                    )}
                  </div>

                  <div>
                    <label htmlFor="modal_term_months" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Loan Term *
                    </label>
                    {loadingEligibility ? (
                      <div className="w-full p-3 border-2 border-blue-300 rounded-xl bg-blue-50">
                        <p className="text-blue-700 text-sm">Loading available terms...</p>
                      </div>
                    ) : loanEligibility?.available_terms?.length ? (
                      <select
                        id="modal_term_months"
                        name="term_months"
                        value={formData.term_months}
                        onChange={handleChange}
                        required
                        className="w-full px-4 py-2 md:py-3 border-2 border-blue-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {loanEligibility.available_terms.map((term: any) => (
                          <option key={term.term_months || 'all'} value={term.term_months || ''}>
                            {term.term_label} - {term.interest_rate}% interest
                          </option>
                        ))}
                      </select>
                    ) : loanEligibility && !loanEligibility.has_credit_rating ? (
                      <div className="w-full p-3 border-2 border-yellow-300 rounded-xl bg-yellow-50">
                        <p className="text-yellow-800 text-sm">{loanEligibility.message || 'No credit rating assigned'}</p>
                      </div>
                    ) : (
                      <select
                        id="modal_term_months"
                        name="term_months"
                        value={formData.term_months}
                        onChange={handleChange}
                        required
                        className="w-full px-4 py-2 md:py-3 border-2 border-blue-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="1">1 Month</option>
                        <option value="2">2 Months</option>
                        <option value="3">3 Months</option>
                        <option value="4">4 Months</option>
                      </select>
                    )}
                  </div>
                </div>

                <div>
                  <label htmlFor="modal_amount" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Loan Amount (K) *
                  </label>
                  <input
                    type="number"
                    id="modal_amount"
                    name="amount"
                    step="0.01"
                    min="0"
                    max={loanEligibility?.max_loan_amount || undefined}
                    value={formData.amount !== undefined && formData.amount !== null ? formData.amount : ''}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-2 md:py-3 border-2 border-blue-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Enter loan amount"
                  />
                  {loanEligibility?.has_credit_rating && (
                    <div className="mt-2 p-3 bg-blue-50 border-2 border-blue-200 rounded-xl">
                      <p className="text-sm md:text-base text-blue-800 font-semibold mb-1">
                        Credit Rating: {loanEligibility.tier_name}
                      </p>
                      <p className="text-sm md:text-base text-blue-700">
                        Savings Balance: K{loanEligibility.savings_balance?.toLocaleString() || '0.00'}
                      </p>
                      <p className="text-sm md:text-base text-blue-700">
                        Multiplier: {loanEligibility.multiplier}x
                      </p>
                      <p className="text-sm md:text-base text-blue-900 font-bold mt-2">
                        Maximum Loan Amount: K{loanEligibility.max_loan_amount?.toLocaleString() || '0.00'}
                      </p>
                      <p className="text-xs md:text-sm text-blue-600 mt-1 italic">
                        Note: Your loan amount cannot exceed {loanEligibility.multiplier}x your total savings balance.
                      </p>
                    </div>
                  )}
                  {(!loanEligibility || !loanEligibility.has_credit_rating) && (
                    <p className="mt-2 text-sm md:text-base text-blue-700">
                      Enter the amount you wish to borrow
                    </p>
                  )}
                </div>

                <div>
                  <label htmlFor="modal_notes" className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Notes (Optional)
                  </label>
                  <textarea
                    id="modal_notes"
                    name="notes"
                    value={formData.notes || ''}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                    rows={3}
                    className="w-full px-4 py-3 border-2 border-blue-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm md:text-base"
                    placeholder="Add any additional notes or remarks about your loan application..."
                  />
                </div>

                <div className="flex flex-col sm:flex-row justify-end gap-3 md:gap-4 pt-6 border-t-2 border-blue-200">
                  {editingApplication ? (
                    <>
                      <button
                        type="button"
                        onClick={handleCancelEdit}
                        className="btn-secondary text-center"
                      >
                        Cancel Edit
                      </button>
                      <button
                        type="submit"
                        disabled={loading}
                        className="btn-primary disabled:opacity-50"
                      >
                        {loading ? 'Updating...' : 'Update Application'}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={closeFormModal}
                        className="btn-secondary text-center"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={loading}
                        className="btn-primary disabled:opacity-50"
                      >
                        {loading ? 'Submitting...' : 'Submit Application'}
                      </button>
                    </>
                  )}
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
