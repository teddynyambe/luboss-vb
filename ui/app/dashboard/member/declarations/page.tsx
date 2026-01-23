'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { memberApi, DeclarationCreate } from '@/lib/memberApi';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface Cycle {
  id: string;
  year: number;
  cycle_number: number;
  start_date: string;
  end_date?: string;
}

interface Declaration {
  id: string;
  cycle_id: string;
  effective_month: string;
  declared_savings_amount?: number;
  declared_social_fund?: number;
  declared_admin_fund?: number;
  declared_penalties?: number;
  declared_interest_on_loan?: number;
  declared_loan_repayment?: number;
  status: string;
  created_at: string;
  updated_at?: string;
  can_edit?: boolean;
}

export default function DeclarationsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [selectedCycle, setSelectedCycle] = useState<string>('');
  const [effectiveMonth, setEffectiveMonth] = useState<string>('');
  const [currentMonthDeclaration, setCurrentMonthDeclaration] = useState<Declaration | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<DeclarationCreate>({
    cycle_id: '',
    effective_month: '',
    declared_savings_amount: undefined,
    declared_social_fund: undefined,
    declared_admin_fund: undefined,
    declared_penalties: undefined,
    declared_interest_on_loan: undefined,
    declared_loan_repayment: undefined,
  });
  const [loading, setLoading] = useState(false);
  const [loadingDeclaration, setLoadingDeclaration] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    loadCycles();
    loadCurrentMonthDeclaration();
    // Set current month as default (first day of current month)
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    setEffectiveMonth(currentMonth);
    setFormData({ ...formData, effective_month: currentMonth });
    
    // Check if we're editing a specific declaration from URL params
    const checkEditParam = () => {
      if (typeof window !== 'undefined') {
        const params = new URLSearchParams(window.location.search);
        const editId = params.get('edit');
        if (editId) {
          loadDeclarationForEdit(editId);
        }
      }
    };
    
    // Delay to ensure cycles are loaded first
    setTimeout(checkEditParam, 500);
  }, []);

  const loadCurrentMonthDeclaration = async () => {
    setLoadingDeclaration(true);
    try {
      const response = await memberApi.getCurrentMonthDeclaration();
      if (response.data) {
        setCurrentMonthDeclaration(response.data);
        // If editing, populate form with existing data
        if (response.data.can_edit) {
          setFormData({
            cycle_id: response.data.cycle_id,
            effective_month: response.data.effective_month,
            declared_savings_amount: response.data.declared_savings_amount,
            declared_social_fund: response.data.declared_social_fund,
            declared_admin_fund: response.data.declared_admin_fund,
            declared_penalties: response.data.declared_penalties,
            declared_interest_on_loan: response.data.declared_interest_on_loan,
            declared_loan_repayment: response.data.declared_loan_repayment,
          });
          setSelectedCycle(response.data.cycle_id);
          setEffectiveMonth(response.data.effective_month);
        }
      } else {
        setCurrentMonthDeclaration(null);
      }
    } catch (err) {
      console.error('Error loading current month declaration:', err);
      setCurrentMonthDeclaration(null);
    } finally {
      setLoadingDeclaration(false);
    }
  };

  const loadDeclarationForEdit = async (declarationId: string) => {
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        const declaration = response.data.find(d => d.id === declarationId);
        if (declaration) {
          // Check if it's the current month and can be edited
          const now = new Date();
          const declarationDate = new Date(declaration.effective_month);
          const isCurrentMonth = declarationDate.getFullYear() === now.getFullYear() && 
                                 declarationDate.getMonth() === now.getMonth();
          const canEdit = isCurrentMonth && now.getDate() <= 20;
          
          if (canEdit) {
            setCurrentMonthDeclaration({ ...declaration, can_edit: true });
            setIsEditing(true);
            setFormData({
              cycle_id: declaration.cycle_id,
              effective_month: declaration.effective_month,
              declared_savings_amount: declaration.declared_savings_amount,
              declared_social_fund: declaration.declared_social_fund,
              declared_admin_fund: declaration.declared_admin_fund,
              declared_penalties: declaration.declared_penalties,
              declared_interest_on_loan: declaration.declared_interest_on_loan,
              declared_loan_repayment: declaration.declared_loan_repayment,
            });
            setSelectedCycle(declaration.cycle_id);
            setEffectiveMonth(declaration.effective_month);
          } else {
            setError('This declaration cannot be edited. Only current month declarations can be edited before the 20th.');
          }
        } else {
          setError('Declaration not found.');
        }
      }
    } catch (err) {
      console.error('Error loading declaration for edit:', err);
      setError('Failed to load declaration for editing.');
    }
  };

  const loadCycles = async () => {
    try {
      // Get active cycles from member API
      const response = await api.get<Cycle[]>('/api/member/cycles');
      if (response.data && response.data.length > 0) {
        setCycles(response.data);
        setSelectedCycle(response.data[0].id);
        setFormData({ ...formData, cycle_id: response.data[0].id });
      } else {
        setError('No active cycles available. Please contact the administrator.');
      }
    } catch (err) {
      console.error('Error loading cycles:', err);
      setError('Unable to load cycles. Please try again later.');
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === 'cycle_id') {
      setSelectedCycle(value);
      setFormData({ ...formData, cycle_id: value });
    } else if (name === 'effective_month') {
      setEffectiveMonth(value);
      setFormData({ ...formData, effective_month: value });
    } else {
      const numValue = value === '' ? undefined : parseFloat(value);
      setFormData({ ...formData, [name]: numValue });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setLoading(true);

    if (!selectedCycle || !effectiveMonth) {
      setError('Please select a cycle and effective month');
      setLoading(false);
      return;
    }

    const declarationData: DeclarationCreate = {
      ...formData,
      cycle_id: selectedCycle,
      effective_month: effectiveMonth,
    };

    try {
      let response;
      if (isEditing && currentMonthDeclaration) {
        // Update existing declaration
        response = await memberApi.updateDeclaration(currentMonthDeclaration.id, declarationData);
        if (response.data) {
          setSuccess(true);
          setIsEditing(false);
          await loadCurrentMonthDeclaration();
          // Clear URL params if editing from list page
          if (typeof window !== 'undefined') {
            window.history.replaceState({}, '', '/dashboard/member/declarations');
          }
        } else {
          setError(response.error || 'Failed to update declaration');
        }
      } else {
        // Create new declaration
        response = await memberApi.createDeclaration(declarationData);
        if (response.data) {
          setSuccess(true);
          await loadCurrentMonthDeclaration();
          setTimeout(() => {
            router.push('/dashboard/member/declarations/list');
          }, 2000);
        } else {
          setError(response.error || 'Failed to create declaration');
        }
      }
    } catch (err) {
      setError('An error occurred while processing the declaration');
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = () => {
    if (currentMonthDeclaration && currentMonthDeclaration.can_edit) {
      setIsEditing(true);
      setFormData({
        cycle_id: currentMonthDeclaration.cycle_id,
        effective_month: currentMonthDeclaration.effective_month,
        declared_savings_amount: currentMonthDeclaration.declared_savings_amount,
        declared_social_fund: currentMonthDeclaration.declared_social_fund,
        declared_admin_fund: currentMonthDeclaration.declared_admin_fund,
        declared_penalties: currentMonthDeclaration.declared_penalties,
        declared_interest_on_loan: currentMonthDeclaration.declared_interest_on_loan,
        declared_loan_repayment: currentMonthDeclaration.declared_loan_repayment,
      });
      setSelectedCycle(currentMonthDeclaration.cycle_id);
      setEffectiveMonth(currentMonthDeclaration.effective_month);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    // Reset form to current month defaults
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    setEffectiveMonth(currentMonth);
    setFormData({
      cycle_id: selectedCycle,
      effective_month: currentMonth,
      declared_savings_amount: undefined,
      declared_social_fund: undefined,
      declared_admin_fund: undefined,
      declared_penalties: undefined,
      declared_interest_on_loan: undefined,
      declared_loan_repayment: undefined,
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
          <nav className="bg-white shadow-lg border-b-2 border-blue-200">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between items-center h-16 md:h-20">
                <div className="flex items-center space-x-3 md:space-x-4">
                  <Link href="/dashboard/member/declarations/list" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                    ← Back to List
                  </Link>
                  <h1 className="text-lg md:text-2xl font-bold text-blue-900">
                    {isEditing ? 'Edit Declaration' : 'Make Declaration'}
                  </h1>
                </div>
              </div>
            </div>
          </nav>

          <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
            <div className="card">
                {success && (
                  <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                    ✓ {isEditing ? 'Declaration updated successfully!' : 'Declaration created successfully!'} {!isEditing && 'Redirecting...'}
                  </div>
                )}

                {error && (
                  <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                    {error}
                  </div>
                )}

                {/* Current Month Declaration Display */}
                {loadingDeclaration ? (
                  <div className="mb-6 text-center py-4">
                    <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-200 border-t-blue-600 mx-auto"></div>
                    <p className="mt-2 text-blue-700 text-sm">Checking for existing declaration...</p>
                  </div>
                ) : currentMonthDeclaration && !isEditing ? (
                  <div className="mb-6 bg-blue-50 border-2 border-blue-300 rounded-xl p-4 md:p-5">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
                      <div>
                        <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-2">
                          Current Month Declaration
                        </h3>
                        <p className="text-sm md:text-base text-blue-700">
                          Effective Month: {new Date(currentMonthDeclaration.effective_month).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}
                        </p>
                        <p className="text-sm text-blue-600 mt-1">
                          Status: <span className="font-semibold capitalize">{currentMonthDeclaration.status}</span>
                        </p>
                      </div>
                      {currentMonthDeclaration.can_edit && (
                        <button
                          onClick={handleEdit}
                          className="btn-primary"
                        >
                          Edit Declaration
                        </button>
                      )}
                      {!currentMonthDeclaration.can_edit && (
                        <span className="px-4 py-2 bg-gray-300 text-gray-600 rounded-lg text-sm font-semibold">
                          Cannot edit after 20th of month
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
                      {currentMonthDeclaration.declared_savings_amount !== null && currentMonthDeclaration.declared_savings_amount !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Savings</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_savings_amount.toLocaleString()}</p>
                        </div>
                      )}
                      {currentMonthDeclaration.declared_social_fund !== null && currentMonthDeclaration.declared_social_fund !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Social Fund</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_social_fund.toLocaleString()}</p>
                        </div>
                      )}
                      {currentMonthDeclaration.declared_admin_fund !== null && currentMonthDeclaration.declared_admin_fund !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Admin Fund</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_admin_fund.toLocaleString()}</p>
                        </div>
                      )}
                      {currentMonthDeclaration.declared_penalties !== null && currentMonthDeclaration.declared_penalties !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Penalties</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_penalties.toLocaleString()}</p>
                        </div>
                      )}
                      {currentMonthDeclaration.declared_interest_on_loan !== null && currentMonthDeclaration.declared_interest_on_loan !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Interest on Loan</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_interest_on_loan.toLocaleString()}</p>
                        </div>
                      )}
                      {currentMonthDeclaration.declared_loan_repayment !== null && currentMonthDeclaration.declared_loan_repayment !== undefined && (
                        <div>
                          <p className="text-xs text-blue-600 font-medium">Loan Repayment</p>
                          <p className="text-base font-bold text-blue-900">K{currentMonthDeclaration.declared_loan_repayment.toLocaleString()}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : !currentMonthDeclaration && !isEditing ? (
                  <div className="mb-6 bg-yellow-50 border-2 border-yellow-300 rounded-xl p-4 md:p-5">
                    <p className="text-base md:text-lg text-yellow-800 font-medium">
                      No declaration for the current month. You can create one below.
                    </p>
                  </div>
                ) : null}

                {(!currentMonthDeclaration || isEditing) && (
                <form onSubmit={handleSubmit} className="space-y-4 md:space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                <div>
                  <label htmlFor="cycle_id" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Cycle *
                  </label>
                  {cycles.length > 0 && selectedCycle ? (
                    <input
                      type="text"
                      id="cycle_id"
                      name="cycle_id"
                      value={cycles.find(c => c.id === selectedCycle) ? `${cycles.find(c => c.id === selectedCycle)!.year} - Cycle ${cycles.find(c => c.id === selectedCycle)!.cycle_number}` : ''}
                      readOnly
                      className="w-full bg-gray-100 cursor-not-allowed"
                    />
                  ) : (
                    <input
                      type="text"
                      id="cycle_id"
                      name="cycle_id"
                      value="No active cycle available"
                      readOnly
                      disabled
                      className="w-full bg-gray-100 cursor-not-allowed opacity-50"
                    />
                  )}
                  <p className="mt-2 text-sm md:text-base text-blue-700">Active cycle (read-only)</p>
                </div>

                <div>
                  <label htmlFor="effective_month" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Effective Month *
                  </label>
                  <input
                    type="date"
                    id="effective_month"
                    name="effective_month"
                    value={effectiveMonth}
                    onChange={handleChange}
                    required
                    className="w-full"
                    placeholder="YYYY-MM-01"
                  />
                  <p className="mt-2 text-sm md:text-base text-blue-700">Select the first day of the month</p>
                </div>
              </div>

              <div className="border-t-2 border-blue-200 pt-4 md:pt-6">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4 md:mb-6">Declaration Amounts</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                  <div>
                    <label htmlFor="declared_savings_amount" className="block text-base font-semibold text-blue-900 mb-2">
                      Savings Amount (K)
                    </label>
                    <input
                      type="number"
                      id="declared_savings_amount"
                      name="declared_savings_amount"
                      step="0.01"
                      min="0"
                      value={formData.declared_savings_amount || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>

                  <div>
                    <label htmlFor="declared_social_fund" className="block text-base font-semibold text-blue-900 mb-2">
                      Social Fund (K)
                    </label>
                    <input
                      type="number"
                      id="declared_social_fund"
                      name="declared_social_fund"
                      step="0.01"
                      min="0"
                      value={formData.declared_social_fund || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>

                  <div>
                    <label htmlFor="declared_admin_fund" className="block text-base font-semibold text-blue-900 mb-2">
                      Admin Fund (K)
                    </label>
                    <input
                      type="number"
                      id="declared_admin_fund"
                      name="declared_admin_fund"
                      step="0.01"
                      min="0"
                      value={formData.declared_admin_fund || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>

                  <div>
                    <label htmlFor="declared_penalties" className="block text-base font-semibold text-blue-900 mb-2">
                      Penalties (K)
                    </label>
                    <input
                      type="number"
                      id="declared_penalties"
                      name="declared_penalties"
                      step="0.01"
                      min="0"
                      value={formData.declared_penalties || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>

                  <div>
                    <label htmlFor="declared_interest_on_loan" className="block text-base font-semibold text-blue-900 mb-2">
                      Interest on Loan (K)
                    </label>
                    <input
                      type="number"
                      id="declared_interest_on_loan"
                      name="declared_interest_on_loan"
                      step="0.01"
                      min="0"
                      value={formData.declared_interest_on_loan || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>

                  <div>
                    <label htmlFor="declared_loan_repayment" className="block text-base font-semibold text-blue-900 mb-2">
                      Loan Repayment (K)
                    </label>
                    <input
                      type="number"
                      id="declared_loan_repayment"
                      name="declared_loan_repayment"
                      step="0.01"
                      min="0"
                      value={formData.declared_loan_repayment || ''}
                      onChange={handleChange}
                      className="w-full"
                      placeholder="0.00"
                    />
                  </div>
                </div>
              </div>

                  <div className="flex flex-col sm:flex-row justify-end gap-3 md:gap-4 pt-6 border-t-2 border-blue-200">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={handleCancelEdit}
                          className="btn-secondary text-center"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={loading}
                          className="btn-primary disabled:opacity-50"
                        >
                          {loading ? 'Updating...' : 'Update Declaration'}
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
                          {loading ? 'Submitting...' : 'Submit Declaration'}
                        </button>
                      </>
                    )}
                  </div>
                </form>
                )}
        </div>
      </main>
    </div>
  );
}
