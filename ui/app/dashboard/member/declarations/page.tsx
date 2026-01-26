'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { memberApi, DeclarationCreate } from '@/lib/memberApi';
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
  const [applicablePenalties, setApplicablePenalties] = useState<{ total_amount: number; penalties: Array<{ id: string | null; penalty_type_name: string; fee_amount: number; date_issued: string | null; notes: string | null; source: string }> } | null>(null);
  const [activeTab, setActiveTab] = useState<'create' | 'list'>('create');
  const [allDeclarations, setAllDeclarations] = useState<Declaration[]>([]);
  const [loadingDeclarations, setLoadingDeclarations] = useState(false);
  const [selectedDeclaration, setSelectedDeclaration] = useState<Declaration | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);

  useEffect(() => {
    loadCycles();
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
        const tab = params.get('tab');
        if (tab === 'list') {
          setActiveTab('list');
          loadAllDeclarations();
        }
        if (editId) {
          loadDeclarationForEdit(editId);
          setActiveTab('create');
        }
      }
    };
    
    // Delay to ensure cycles are loaded first
    setTimeout(checkEditParam, 500);
    loadCurrentMonthDeclaration();
  }, []);

  // Check for late declaration penalty when cycle or effective month changes (only for new declarations)
  const loadApplicablePenalties = async () => {
    if (!selectedCycle || !effectiveMonth) {
      setApplicablePenalties(null);
      return;
    }
    
    try {
      // Ensure effectiveMonth is in YYYY-MM-DD format
      const effectiveDate = effectiveMonth.includes('T') ? effectiveMonth.split('T')[0] : effectiveMonth;
      const response = await api.get<{ total_amount: number; penalties: Array<{ id: string | null; penalty_type_name: string; fee_amount: number; date_issued: string | null; notes: string | null; source: string }> }>(
        `/api/member/declarations/applicable-penalties?cycle_id=${selectedCycle}&effective_month=${effectiveDate}`
      );
      if (response.data) {
        setApplicablePenalties(response.data);
      } else {
        setApplicablePenalties(null);
      }
    } catch (err) {
      console.error('Error loading applicable penalties:', err);
      setApplicablePenalties(null);
    }
  };

  // Load applicable penalties when cycle or effective month changes (only for new declarations)
  useEffect(() => {
    if (selectedCycle && effectiveMonth && !isEditing && !currentMonthDeclaration) {
      loadApplicablePenalties();
    }
  }, [selectedCycle, effectiveMonth, isEditing, currentMonthDeclaration]);

  // Auto-populate penalties when they're loaded and no declaration exists
  useEffect(() => {
    if (applicablePenalties && !currentMonthDeclaration && !isEditing) {
      if (applicablePenalties.total_amount > 0) {
        setFormData(prev => ({
          ...prev,
          declared_penalties: applicablePenalties.total_amount
        }));
      }
    }
  }, [applicablePenalties, currentMonthDeclaration, isEditing]);

  const loadCurrentMonthDeclaration = async () => {
    setLoadingDeclaration(true);
    try {
      const response = await memberApi.getCurrentMonthDeclaration();
      if (response.data) {
        setCurrentMonthDeclaration(response.data);
        // If editing, populate form with existing data
        const declarationData = response.data as {
          can_edit?: boolean;
          cycle_id?: string;
          effective_month?: string;
          declared_savings_amount?: number;
          declared_social_fund?: number;
          declared_admin_fund?: number;
          declared_penalties?: number;
          declared_interest_on_loan?: number;
          declared_loan_repayment?: number;
        };
        if (declarationData.can_edit) {
          const cycleId = declarationData.cycle_id ?? '';
          const effectiveMonth = declarationData.effective_month ?? '';
          setFormData({
            cycle_id: cycleId,
            effective_month: effectiveMonth,
            declared_savings_amount: declarationData.declared_savings_amount ?? 0,
            declared_social_fund: declarationData.declared_social_fund ?? 0,
            declared_admin_fund: declarationData.declared_admin_fund ?? 0,
            declared_penalties: declarationData.declared_penalties ?? 0,
            declared_interest_on_loan: declarationData.declared_interest_on_loan ?? 0,
            declared_loan_repayment: declarationData.declared_loan_repayment ?? 0,
          });
          setSelectedCycle(cycleId);
          setEffectiveMonth(effectiveMonth);
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

  const loadAllDeclarations = async () => {
    setLoadingDeclarations(true);
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        setAllDeclarations(response.data);
      }
    } catch (err) {
      console.error('Error loading declarations:', err);
      setError('Failed to load declarations.');
    } finally {
      setLoadingDeclarations(false);
    }
  };

  const handleEditFromList = (declaration: Declaration) => {
    if (declaration.can_edit) {
      setActiveTab('create');
      loadDeclarationForEdit(declaration.id);
    }
  };

  const handleViewFromList = (declaration: Declaration) => {
    setSelectedDeclaration(declaration);
    setShowDetailsModal(true);
  };

  const closeDetailsModal = () => {
    setShowDetailsModal(false);
    setSelectedDeclaration(null);
  };

  const copyDeclarationDetails = () => {
    if (!selectedDeclaration) return;
    
    const total = (
      (selectedDeclaration.declared_savings_amount || 0) +
      (selectedDeclaration.declared_social_fund || 0) +
      (selectedDeclaration.declared_admin_fund || 0) +
      (selectedDeclaration.declared_penalties || 0) +
      (selectedDeclaration.declared_interest_on_loan || 0) +
      (selectedDeclaration.declared_loan_repayment || 0)
    );

    const statusText = selectedDeclaration.status === 'proof' 
      ? 'Proof Submitted' 
      : selectedDeclaration.status.charAt(0).toUpperCase() + selectedDeclaration.status.slice(1);

    const text = `DECLARATION DETAILS

Effective Month: ${formatMonth(selectedDeclaration.effective_month)}
Status: ${statusText}
Created: ${formatDate(selectedDeclaration.created_at)}
${selectedDeclaration.updated_at ? `Last Updated: ${formatDate(selectedDeclaration.updated_at)}` : ''}

DECLARATION AMOUNTS:
• Savings Amount: ${selectedDeclaration.declared_savings_amount !== null && selectedDeclaration.declared_savings_amount !== undefined ? `K${selectedDeclaration.declared_savings_amount.toLocaleString()}` : 'Not declared'}
• Social Fund: ${selectedDeclaration.declared_social_fund !== null && selectedDeclaration.declared_social_fund !== undefined ? `K${selectedDeclaration.declared_social_fund.toLocaleString()}` : 'Not declared'}
• Admin Fund: ${selectedDeclaration.declared_admin_fund !== null && selectedDeclaration.declared_admin_fund !== undefined ? `K${selectedDeclaration.declared_admin_fund.toLocaleString()}` : 'Not declared'}
• Penalties: ${selectedDeclaration.declared_penalties !== null && selectedDeclaration.declared_penalties !== undefined ? `K${selectedDeclaration.declared_penalties.toLocaleString()}` : 'Not declared'}
• Interest on Loan: ${selectedDeclaration.declared_interest_on_loan !== null && selectedDeclaration.declared_interest_on_loan !== undefined ? `K${selectedDeclaration.declared_interest_on_loan.toLocaleString()}` : 'Not declared'}
• Loan Repayment: ${selectedDeclaration.declared_loan_repayment !== null && selectedDeclaration.declared_loan_repayment !== undefined ? `K${selectedDeclaration.declared_loan_repayment.toLocaleString()}` : 'Not declared'}

TOTAL DECLARED AMOUNT: K${total.toLocaleString()}`;

    navigator.clipboard.writeText(text).then(() => {
      setSuccess(true);
      setError('');
      setTimeout(() => setSuccess(false), 3000);
    }).catch(() => {
      setError('Failed to copy to clipboard');
      setSuccess(false);
    });
  };

  const loadDeclarationForEdit = async (declarationId: string) => {
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        const declarations = Array.isArray(response.data) ? response.data : [];
        const declaration = declarations.find(d => d.id === declarationId);
        if (declaration) {
          // Check if it's the current month and can be edited
          // Parse date string (YYYY-MM-DD) without timezone conversion
          const [year, month] = declaration.effective_month.split('-').map(Number);
          const declarationDate = new Date(year, month - 1, 1); // month is 0-indexed
          const now = new Date();
          const isCurrentMonth = declarationDate.getFullYear() === now.getFullYear() && 
                                 declarationDate.getMonth() === now.getMonth();
          // Removed 20th day restriction - can edit current month declarations anytime
          const canEdit = isCurrentMonth;
          
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
            setError('This declaration cannot be edited. Only current month declarations can be edited.');
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
        const firstCycleId = response.data[0].id;
        setSelectedCycle(firstCycleId);
        setFormData({ ...formData, cycle_id: firstCycleId });
        // Load applicable penalties after cycle is loaded
        if (effectiveMonth) {
          setTimeout(() => loadApplicablePenalties(), 200);
        }
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
      // Reload applicable penalties when effective month changes
      if (selectedCycle && value) {
        setTimeout(() => loadApplicablePenalties(), 100);
      }
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

  const formatDate = (dateString: string) => {
    if (!dateString) return 'Invalid Date';
    // Handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS" formats
    const datePart = dateString.split('T')[0].split(' ')[0]; // Get just the date part
    const parts = datePart.split('-');
    if (parts.length !== 3) return 'Invalid Date';
    const [year, month, day] = parts.map(Number);
    if (isNaN(year) || isNaN(month) || isNaN(day)) return 'Invalid Date';
    const date = new Date(year, month - 1, day); // month is 0-indexed
    if (isNaN(date.getTime())) return 'Invalid Date';
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const formatMonth = (dateString: string) => {
    // Parse date string (YYYY-MM-DD) without timezone conversion
    // Handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS" formats
    const datePart = dateString.split('T')[0].split(' ')[0]; // Get just the date part
    const [year, month] = datePart.split('-').map(Number);
    
    // Format month name directly without Date object to avoid timezone issues
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    
    if (month >= 1 && month <= 12 && year) {
      return `${monthNames[month - 1]} ${year}`;
    }
    
    // Fallback to Date if parsing fails
    const date = new Date(year, month - 1, 1);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  };

  const isCurrentMonth = (dateString: string) => {
    // Parse date string (YYYY-MM-DD) without timezone conversion
    const [year, month] = dateString.split('-').map(Number);
    const date = new Date(year, month - 1, 1);
    const now = new Date();
    return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
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
                  <h1 className="text-lg md:text-2xl font-bold text-blue-900">Monthly Declarations</h1>
                </div>
                <UserMenu />
              </div>
            </div>
          </nav>

          <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
            {/* Tab Navigation */}
            <div className="card mb-4">
              <div className="flex space-x-2 border-b-2 border-blue-200">
                <button
                  onClick={() => {
                    setActiveTab('create');
                    setError('');
                    setSuccess(false);
                  }}
                  className={`px-6 py-3 font-semibold text-base md:text-lg transition-colors ${
                    activeTab === 'create'
                      ? 'text-blue-600 border-b-4 border-blue-600'
                      : 'text-blue-400 hover:text-blue-600'
                  }`}
                >
                  {isEditing ? 'Edit Declaration' : 'Create/Edit Declaration'}
                </button>
                <button
                  onClick={() => {
                    setActiveTab('list');
                    loadAllDeclarations();
                    setError('');
                    setSuccess(false);
                  }}
                  className={`px-6 py-3 font-semibold text-base md:text-lg transition-colors ${
                    activeTab === 'list'
                      ? 'text-blue-600 border-b-4 border-blue-600'
                      : 'text-blue-400 hover:text-blue-600'
                  }`}
                >
                  View All Declarations
                </button>
              </div>
            </div>

            {/* Tab Content */}
            {activeTab === 'create' ? (
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
                          Effective Month: {formatMonth(currentMonthDeclaration.effective_month)}
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
                          Cannot edit previous month declarations
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
                      Penalties (K) {applicablePenalties && applicablePenalties.total_amount > 0 ? (
                        <span className="text-sm font-normal text-blue-600">(Auto-filled - read-only)</span>
                      ) : null}
                    </label>
                    <input
                      type="number"
                      id="declared_penalties"
                      name="declared_penalties"
                      step="0.01"
                      min="0"
                      value={formData.declared_penalties || ''}
                      onChange={handleChange}
                      readOnly
                      className="w-full bg-gray-100 cursor-not-allowed"
                      placeholder="0.00"
                    />
                    {applicablePenalties && applicablePenalties.penalties.length > 0 ? (
                      <div className="mt-2 p-3 bg-blue-50 border-2 border-blue-200 rounded-lg space-y-2">
                        <div>
                          <p className="text-xs font-semibold text-blue-900 mb-2">Applicable Penalties:</p>
                          <ul className="space-y-1 text-xs text-blue-700">
                            {applicablePenalties.penalties.map((penalty, index) => (
                              <li key={penalty.id || `penalty-${index}`}>
                                • {penalty.penalty_type_name}: K{penalty.fee_amount.toLocaleString()}
                                {penalty.notes && <span className="text-blue-600"> ({penalty.notes})</span>}
                                {penalty.source === 'late_declaration' && (
                                  <span className="text-blue-600 italic"> - Late Declaration</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <p className="mt-2 pt-2 border-t border-blue-300 text-xs font-semibold text-blue-900">
                          Total Penalties: K{applicablePenalties.total_amount.toLocaleString()}
                        </p>
                      </div>
                    ) : (
                      <p className="mt-1 text-sm text-blue-600">No penalties applicable</p>
                    )}
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
            ) : (
              <div className="card">
                {loadingDeclarations ? (
                  <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                    <p className="mt-4 text-blue-700 text-lg">Loading declarations...</p>
                  </div>
                ) : allDeclarations.length === 0 ? (
                  <div className="text-center py-12">
                    <div className="mb-6">
                      <svg className="mx-auto h-24 w-24 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4">No Declarations Found</h2>
                    <p className="text-lg md:text-xl text-blue-700 mb-6">
                      You haven't made any declarations yet.
                    </p>
                    <button
                      onClick={() => setActiveTab('create')}
                      className="btn-primary inline-block"
                    >
                      Create Your First Declaration
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                      <div className="flex flex-wrap items-center gap-4">
                        <h2 className="text-xl md:text-2xl font-bold text-blue-900">
                          All Declarations ({allDeclarations.length})
                        </h2>
                        <div className="flex flex-wrap items-center gap-4 text-sm md:text-base">
                          <span className="text-blue-600">
                            <span className="font-medium">Total:</span> <span className="font-bold text-blue-900">{allDeclarations.length}</span>
                          </span>
                          <span className="text-yellow-600">
                            <span className="font-medium">Pending:</span> <span className="font-bold text-yellow-700">{allDeclarations.filter(d => d.status === 'pending').length}</span>
                          </span>
                          <span className="text-green-600">
                            <span className="font-medium">Approved:</span> <span className="font-bold text-green-700">{allDeclarations.filter(d => d.status === 'approved').length}</span>
                          </span>
                          <span className="text-blue-600">
                            <span className="font-medium">Current Month:</span> <span className="font-bold text-blue-700">{allDeclarations.filter(d => isCurrentMonth(d.effective_month)).length}</span>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="bg-blue-100 border-b-2 border-blue-300">
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Effective Month
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Savings
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Social Fund
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Admin Fund
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Status
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Created
                            </th>
                            <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                              Actions
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {allDeclarations.map((declaration) => {
                            const isCurrent = isCurrentMonth(declaration.effective_month);
                            return (
                              <tr
                                key={declaration.id}
                                className={`border-b border-blue-200 hover:bg-blue-50 transition-colors ${
                                  isCurrent ? 'bg-blue-50' : ''
                                }`}
                              >
                                <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                                  <div className="font-semibold">{formatMonth(declaration.effective_month)}</div>
                                  {isCurrent && (
                                    <span className="inline-block mt-1 px-2 py-1 bg-blue-200 text-blue-800 text-xs rounded-full font-semibold">
                                      Current Month
                                    </span>
                                  )}
                                </td>
                                <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                                  {declaration.declared_savings_amount !== null && declaration.declared_savings_amount !== undefined
                                    ? `K${declaration.declared_savings_amount.toLocaleString()}`
                                    : '-'}
                                </td>
                                <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                                  {declaration.declared_social_fund !== null && declaration.declared_social_fund !== undefined
                                    ? `K${declaration.declared_social_fund.toLocaleString()}`
                                    : '-'}
                                </td>
                                <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                                  {declaration.declared_admin_fund !== null && declaration.declared_admin_fund !== undefined
                                    ? `K${declaration.declared_admin_fund.toLocaleString()}`
                                    : '-'}
                                </td>
                                <td className="p-3 md:p-4">
                                  <span
                                    className={`inline-block px-3 py-1 rounded-full text-xs md:text-sm font-semibold ${
                                      declaration.status === 'pending'
                                        ? 'bg-yellow-200 text-yellow-800'
                                        : declaration.status === 'proof'
                                        ? 'bg-blue-200 text-blue-800'
                                        : declaration.status === 'approved'
                                        ? 'bg-green-200 text-green-800'
                                        : declaration.status === 'rejected'
                                        ? 'bg-red-200 text-red-800'
                                        : 'bg-gray-200 text-gray-800'
                                    }`}
                                  >
                                    {declaration.status === 'proof' ? 'Proof Submitted' : declaration.status.charAt(0).toUpperCase() + declaration.status.slice(1)}
                                  </span>
                                </td>
                                <td className="p-3 md:p-4 text-sm md:text-base text-blue-800">
                                  {formatDate(declaration.created_at)}
                                </td>
                                <td className="p-3 md:p-4">
                                  <div className="flex flex-col sm:flex-row gap-2">
                                    {isCurrent && declaration.can_edit && (
                                      <button
                                        onClick={() => handleEditFromList(declaration)}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                                      >
                                        Edit
                                      </button>
                                    )}
                                    {(isCurrent && !declaration.can_edit) || !isCurrent ? (
                                      <button
                                        onClick={() => handleViewFromList(declaration)}
                                        className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm font-semibold transition-colors"
                                      >
                                        View Details
                                      </button>
                                    ) : null}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </main>

      {/* Declaration Details Modal */}
      {showDetailsModal && selectedDeclaration && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Declaration Details</h2>
              <div className="flex items-center gap-3">
                <button
                  onClick={copyDeclarationDetails}
                  className="text-white hover:text-blue-200 transition-colors p-2 rounded-lg hover:bg-blue-700"
                  title="Copy declaration details"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
                <button
                  onClick={closeDetailsModal}
                  className="text-white hover:text-blue-200 text-2xl font-bold"
                >
                  ×
                </button>
              </div>
            </div>
            
            <div className="p-6 md:p-8 space-y-6">
              {/* Success/Error Messages */}
              {success && (
                <div className="bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 rounded-lg">
                  ✓ Declaration details copied to clipboard!
                </div>
              )}
              {error && (
                <div className="bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 rounded-lg">
                  {error}
                </div>
              )}
              {/* Header Info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-4 border-b-2 border-blue-200">
                <div>
                  <p className="text-sm text-blue-600 font-medium mb-1">Effective Month</p>
                  <p className="text-lg font-bold text-blue-900">{formatMonth(selectedDeclaration.effective_month)}</p>
                </div>
                <div>
                  <p className="text-sm text-blue-600 font-medium mb-1">Status</p>
                  <span
                    className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${
                      selectedDeclaration.status === 'pending'
                        ? 'bg-yellow-200 text-yellow-800'
                        : selectedDeclaration.status === 'proof'
                        ? 'bg-blue-200 text-blue-800'
                        : selectedDeclaration.status === 'approved'
                        ? 'bg-green-200 text-green-800'
                        : selectedDeclaration.status === 'rejected'
                        ? 'bg-red-200 text-red-800'
                        : 'bg-gray-200 text-gray-800'
                    }`}
                  >
                    {selectedDeclaration.status === 'proof' ? 'Proof Submitted' : selectedDeclaration.status.charAt(0).toUpperCase() + selectedDeclaration.status.slice(1)}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-blue-600 font-medium mb-1">Created</p>
                  <p className="text-base text-blue-900">{formatDate(selectedDeclaration.created_at)}</p>
                </div>
                {selectedDeclaration.updated_at && (
                  <div>
                    <p className="text-sm text-blue-600 font-medium mb-1">Last Updated</p>
                    <p className="text-base text-blue-900">{formatDate(selectedDeclaration.updated_at)}</p>
                  </div>
                )}
              </div>

              {/* Declaration Amounts */}
              <div>
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Declaration Amounts</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <p className="text-sm text-blue-600 font-medium mb-2">Savings Amount</p>
                    <p className="text-2xl font-bold text-blue-900">
                      {selectedDeclaration.declared_savings_amount !== null && selectedDeclaration.declared_savings_amount !== undefined
                        ? `K${selectedDeclaration.declared_savings_amount.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                  
                  <div className="bg-purple-50 border-2 border-purple-200 rounded-xl p-4">
                    <p className="text-sm text-purple-600 font-medium mb-2">Social Fund</p>
                    <p className="text-2xl font-bold text-purple-900">
                      {selectedDeclaration.declared_social_fund !== null && selectedDeclaration.declared_social_fund !== undefined
                        ? `K${selectedDeclaration.declared_social_fund.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                  
                  <div className="bg-indigo-50 border-2 border-indigo-200 rounded-xl p-4">
                    <p className="text-sm text-indigo-600 font-medium mb-2">Admin Fund</p>
                    <p className="text-2xl font-bold text-indigo-900">
                      {selectedDeclaration.declared_admin_fund !== null && selectedDeclaration.declared_admin_fund !== undefined
                        ? `K${selectedDeclaration.declared_admin_fund.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                  
                  <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
                    <p className="text-sm text-yellow-600 font-medium mb-2">Penalties</p>
                    <p className="text-2xl font-bold text-yellow-900">
                      {selectedDeclaration.declared_penalties !== null && selectedDeclaration.declared_penalties !== undefined
                        ? `K${selectedDeclaration.declared_penalties.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                  
                  <div className="bg-green-50 border-2 border-green-200 rounded-xl p-4">
                    <p className="text-sm text-green-600 font-medium mb-2">Interest on Loan</p>
                    <p className="text-2xl font-bold text-green-900">
                      {selectedDeclaration.declared_interest_on_loan !== null && selectedDeclaration.declared_interest_on_loan !== undefined
                        ? `K${selectedDeclaration.declared_interest_on_loan.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                  
                  <div className="bg-red-50 border-2 border-red-200 rounded-xl p-4">
                    <p className="text-sm text-red-600 font-medium mb-2">Loan Repayment</p>
                    <p className="text-2xl font-bold text-red-900">
                      {selectedDeclaration.declared_loan_repayment !== null && selectedDeclaration.declared_loan_repayment !== undefined
                        ? `K${selectedDeclaration.declared_loan_repayment.toLocaleString()}`
                        : 'Not declared'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Total Summary */}
              <div className="bg-gradient-to-br from-blue-100 to-blue-200 border-2 border-blue-300 rounded-xl p-4 md:p-6">
                <h3 className="text-lg font-bold text-blue-900 mb-3">Total Declared Amount</h3>
                <p className="text-3xl font-bold text-blue-900">
                  K{(
                    (selectedDeclaration.declared_savings_amount || 0) +
                    (selectedDeclaration.declared_social_fund || 0) +
                    (selectedDeclaration.declared_admin_fund || 0) +
                    (selectedDeclaration.declared_penalties || 0) +
                    (selectedDeclaration.declared_interest_on_loan || 0) +
                    (selectedDeclaration.declared_loan_repayment || 0)
                  ).toLocaleString()}
                </p>
              </div>

              {/* Footer */}
              <div className="flex justify-end pt-4 border-t-2 border-blue-200">
                <button
                  onClick={closeDetailsModal}
                  className="btn-primary"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
