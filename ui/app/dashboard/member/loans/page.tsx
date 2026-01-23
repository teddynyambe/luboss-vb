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
        loadLoanEligibility(currentCycle.id);
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

  const loadLoanEligibility = async (cycleId: string) => {
    if (!cycleId) return;
    setLoadingEligibility(true);
    try {
      const response = await api.get(`/api/member/loans/eligibility/${cycleId}`);
      if (response.data) {
        setLoanEligibility(response.data);
        // If available terms exist, set the first one as default
        if (response.data.available_terms && response.data.available_terms.length > 0) {
          const firstTerm = response.data.available_terms[0];
          if (firstTerm.term_months) {
            setFormData({ ...formData, term_months: firstTerm.term_months });
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

    const loanData: LoanApplicationCreate = {
      cycle_id: selectedCycle,
      amount: formData.amount,
      term_months: formData.term_months,
      notes: formData.notes || undefined,
    };

    try {
      let response;
      if (editingApplication) {
        // Update existing application
        response = await memberApi.updateLoanApplication(editingApplication, loanData);
        if (response.data) {
          setSuccess(true);
          setEditingApplication(null);
          setEditingData(null);
          setFormData({ cycle_id: selectedCycle, amount: 0, term_months: '1', notes: '' });
          await loadMyLoans();
          await loadCurrentLoan();
          setTimeout(() => {
            setSuccess(false);
          }, 3000);
        } else {
          setError(response.error || 'Failed to update loan application');
        }
      } else {
        // Create new application
        response = await memberApi.applyForLoan(loanData);
        if (response.data) {
          setSuccess(true);
          setFormData({ cycle_id: selectedCycle, amount: 0, term_months: '1', notes: '' });
          await loadMyLoans();
          await loadCurrentLoan();
          setTimeout(() => {
            setSuccess(false);
          }, 3000);
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

  const handleEdit = (application: any) => {
    setEditingApplication(application.id);
    setEditingData({
      cycle_id: application.cycle_id,
      amount: application.amount,
      term_months: application.term_months,
      notes: application.notes || '',
    });
    setFormData({
      cycle_id: application.cycle_id,
      amount: application.amount,
      term_months: application.term_months,
      notes: application.notes || '',
    });
    // Scroll to form
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCancelEdit = () => {
    setEditingApplication(null);
    setEditingData(null);
    setFormData({ cycle_id: selectedCycle, amount: 0, term_months: '1', notes: '' });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
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

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="space-y-4 md:space-y-6">
          {/* Application Form */}
          <div className="card">
            {success && (
              <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                ✓ {editingApplication ? 'Loan application updated successfully!' : 'Loan application submitted successfully!'}
              </div>
            )}

            {error && (
              <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4 md:space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                <div>
                  <label htmlFor="cycle_id" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Cycle *
                  </label>
                  {selectedCycle && cycles.length > 0 ? (
                    <input
                      type="text"
                      id="cycle_id"
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
                      id="cycle_id"
                      name="cycle_id"
                      value="No active cycle available"
                      readOnly
                      className="w-full bg-gray-100 border-2 border-gray-300 rounded-xl px-4 py-2 text-gray-500 cursor-not-allowed"
                    />
                  )}
                </div>

                <div>
                  <label htmlFor="term_months" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Loan Term *
                  </label>
                  {loadingEligibility ? (
                    <div className="w-full p-3 border-2 border-blue-300 rounded-xl bg-blue-50">
                      <p className="text-blue-700 text-sm">Loading available terms...</p>
                    </div>
                  ) : loanEligibility && loanEligibility.available_terms && loanEligibility.available_terms.length > 0 ? (
                    <select
                      id="term_months"
                      name="term_months"
                      value={formData.term_months}
                      onChange={handleChange}
                      required
                      className="w-full"
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
                      id="term_months"
                      name="term_months"
                      value={formData.term_months}
                      onChange={handleChange}
                      required
                      className="w-full"
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
                <label htmlFor="amount" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Loan Amount (K) *
                </label>
                <input
                  type="number"
                  id="amount"
                  name="amount"
                  step="0.01"
                  min="0"
                  max={loanEligibility?.max_loan_amount || undefined}
                  value={formData.amount || ''}
                  onChange={handleChange}
                  required
                  className="w-full"
                  placeholder="Enter loan amount"
                />
                {loanEligibility && loanEligibility.has_credit_rating && (
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

              <div className="mb-4 md:mb-6">
                <label htmlFor="notes" className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                  Notes (Optional)
                </label>
                <textarea
                  id="notes"
                  name="notes"
                  value={formData.notes || ''}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  rows={4}
                  className="w-full px-4 py-3 border-2 border-blue-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm md:text-base"
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
                    <Link
                      href="/dashboard/member"
                      className="btn-secondary text-center"
                    >
                      Cancel
                    </Link>
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
                
                {currentLoan.repayments && currentLoan.repayments.length > 0 && (
                  <div>
                    <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-3">Repayment History</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="bg-blue-100 border-b-2 border-blue-300">
                            <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Date</th>
                            <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Principal</th>
                            <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Interest</th>
                            <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentLoan.repayments.map((repayment: any, index: number) => (
                            <tr key={index} className="border-b border-blue-200">
                              <td className="p-3 text-sm md:text-base text-blue-800">
                                {repayment.date ? new Date(repayment.date).toLocaleDateString() : 'N/A'}
                              </td>
                              <td className="p-3 text-sm md:text-base text-blue-800">
                                K{repayment.principal?.toLocaleString() || '0.00'}
                              </td>
                              <td className="p-3 text-sm md:text-base text-blue-800">
                                K{repayment.interest?.toLocaleString() || '0.00'}
                              </td>
                              <td className="p-3 text-sm md:text-base font-semibold text-blue-900">
                                K{repayment.total?.toLocaleString() || '0.00'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {/* My Loans */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">My Loans</h2>
            {loadingLoans ? (
              <div className="text-center py-8 md:py-12">
                <div className="animate-spin rounded-full h-12 w-12 md:h-16 md:w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : myLoans.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">No loans yet.</p>
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
                              {loan.application_date ? new Date(loan.application_date).toLocaleDateString() : 'N/A'}
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
    </div>
  );
}
