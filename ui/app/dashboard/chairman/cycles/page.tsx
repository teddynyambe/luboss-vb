'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface Cycle {
  id: string;
  year: string;
  start_date: string;
  end_date: string;
  status: string;
  created_at: string;
  social_fund_required?: number | null;
  admin_fund_required?: number | null;
  phases?: Phase[];
  credit_rating_scheme?: CreditRatingScheme;
}

interface Phase {
  id: string;
  phase_type: string;
  monthly_start_day: number | null;
}

interface CreditRatingTier {
  id?: string;
  tier_name: string;
  tier_order: number;
  description?: string;
  multiplier: number;
  interest_ranges: InterestRateRange[];
}

interface InterestRateRange {
  id?: string;
  term_months?: string | null;
  effective_rate_percent: number;
}

interface CreditRatingScheme {
  id: string;
  name: string;
  description?: string;
  tiers: CreditRatingTier[];
}

export default function ManageCyclesPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingCycleId, setEditingCycleId] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [reopening, setReopening] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form state
  const [year, setYear] = useState('');
  const [startDate, setStartDate] = useState('');
  const [socialFundRequired, setSocialFundRequired] = useState('');
  const [adminFundRequired, setAdminFundRequired] = useState('');
  const [declarationStartDay, setDeclarationStartDay] = useState<number>(1);
  const [loanApplicationStartDay, setLoanApplicationStartDay] = useState<number>(1);
  const [depositsStartDay, setDepositsStartDay] = useState<number>(1);
  
  // Credit rating scheme
  const [schemeName, setSchemeName] = useState('');
  const [schemeDescription, setSchemeDescription] = useState('');
  const [tiers, setTiers] = useState<CreditRatingTier[]>([
    {
      tier_name: '',
      tier_order: 1,
      description: '',
      multiplier: 2.0,
      interest_ranges: [{ term_months: null, effective_rate_percent: 12 }]
    }
  ]);

  useEffect(() => {
    loadCycles();
  }, []);

  const loadCycles = async () => {
    try {
      const response = await api.get<Cycle[]>('/api/chairman/cycles');
      if (response.data) {
        setCycles(response.data);
      } else {
        setError(response.error || 'Failed to load cycles');
      }
    } catch (err) {
      setError('Error loading cycles');
    } finally {
      setLoading(false);
    }
  };

  const handleAddTier = () => {
    setTiers([
      ...tiers,
      {
        tier_name: '',
        tier_order: tiers.length + 1,
        description: '',
        multiplier: 2.0,
        interest_ranges: [{ term_months: null, effective_rate_percent: 12 }]
      }
    ]);
  };

  const handleRemoveTier = (index: number) => {
    setTiers(tiers.filter((_, i) => i !== index));
  };

  const handleUpdateTier = (index: number, field: string, value: any) => {
    const updated = [...tiers];
    updated[index] = { ...updated[index], [field]: value };
    setTiers(updated);
  };

  const handleAddInterestRange = (tierIndex: number) => {
    const updated = [...tiers];
    updated[tierIndex].interest_ranges.push({
      term_months: null,
      effective_rate_percent: 12
    });
    setTiers(updated);
  };

  const handleRemoveInterestRange = (tierIndex: number, rangeIndex: number) => {
    const updated = [...tiers];
    updated[tierIndex].interest_ranges = updated[tierIndex].interest_ranges.filter(
      (_, i) => i !== rangeIndex
    );
    setTiers(updated);
  };

  const handleUpdateInterestRange = (
    tierIndex: number,
    rangeIndex: number,
    field: string,
    value: any
  ) => {
    const updated = [...tiers];
    updated[tierIndex].interest_ranges[rangeIndex] = {
      ...updated[tierIndex].interest_ranges[rangeIndex],
      [field]: value
    };
    setTiers(updated);
  };

  const resetForm = () => {
    setYear('');
    setStartDate('');
    setSocialFundRequired('');
    setAdminFundRequired('');
    setDeclarationStartDay(1);
    setLoanApplicationStartDay(1);
    setDepositsStartDay(1);
    setSchemeName('');
    setSchemeDescription('');
    setTiers([{
      tier_name: '',
      tier_order: 1,
      description: '',
      multiplier: 2.0,
      interest_ranges: [{ term_months: null, effective_rate_percent: 12 }]
    }]);
    setEditingCycleId(null);
  };

  const loadCycleForEdit = async (cycleId: string) => {
    try {
      const response = await api.get<Cycle>(`/api/chairman/cycles/${cycleId}`);
      if (response.data) {
        const cycle = response.data;
        setYear(cycle.year);
        // Handle date format (could be ISO string or date string)
        const dateStr = cycle.start_date.includes('T') 
          ? cycle.start_date.split('T')[0] 
          : cycle.start_date.split(' ')[0];
        setStartDate(dateStr);
        setSocialFundRequired(cycle.social_fund_required?.toString() || '');
        setAdminFundRequired(cycle.admin_fund_required?.toString() || '');
        setEditingCycleId(cycleId);
        setShowCreateForm(true);
        
        // Load phase configs
        if (cycle.phases && cycle.phases.length > 0) {
          cycle.phases.forEach(phase => {
            if (phase.phase_type === 'declaration') {
              setDeclarationStartDay(phase.monthly_start_day || 1);
            } else if (phase.phase_type === 'loan_application') {
              setLoanApplicationStartDay(phase.monthly_start_day || 1);
            } else if (phase.phase_type === 'deposits') {
              setDepositsStartDay(phase.monthly_start_day || 1);
            }
          });
        }
        
        // Load credit rating scheme if exists
        if (cycle.credit_rating_scheme) {
          setSchemeName(cycle.credit_rating_scheme.name);
          setSchemeDescription(cycle.credit_rating_scheme.description || '');
          setTiers(cycle.credit_rating_scheme.tiers.map(tier => ({
            id: tier.id,
            tier_name: tier.tier_name,
            tier_order: tier.tier_order,
            description: tier.description || '',
            multiplier: typeof tier.multiplier === 'number' ? tier.multiplier : parseFloat(tier.multiplier.toString()),
            interest_ranges: tier.interest_ranges?.map(range => ({
              id: range.id,
              term_months: range.term_months || null,
              effective_rate_percent: typeof range.effective_rate_percent === 'number' 
                ? range.effective_rate_percent 
                : parseFloat(range.effective_rate_percent.toString())
            })) || []
          })));
        }
      } else {
        setError(response.error || 'Failed to load cycle details');
      }
    } catch (err) {
      setError('Error loading cycle details');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Validation
    if (!year || !startDate) {
      setError('Please fill in year and start date');
      return;
    }

    if (declarationStartDay < 1 || declarationStartDay > 31 ||
        loanApplicationStartDay < 1 || loanApplicationStartDay > 31 ||
        depositsStartDay < 1 || depositsStartDay > 31) {
      setError('Phase start days must be between 1 and 31');
      return;
    }

    if (schemeName && tiers.some(t => !t.tier_name || t.multiplier <= 0)) {
      setError('Please fill in all credit rating tier details');
      return;
    }

    const cycleData = {
      cycle: {
        year,
        start_date: startDate,
        social_fund_required: socialFundRequired ? parseFloat(socialFundRequired) : undefined,
        admin_fund_required: adminFundRequired ? parseFloat(adminFundRequired) : undefined
      },
      phase_configs: [
        { phase_type: 'declaration', monthly_start_day: declarationStartDay },
        { phase_type: 'loan_application', monthly_start_day: loanApplicationStartDay },
        { phase_type: 'deposits', monthly_start_day: depositsStartDay }
      ],
      credit_rating_scheme: schemeName ? {
        name: schemeName,
        description: schemeDescription || undefined,
        tiers: tiers.map(t => ({
          tier_name: t.tier_name,
          tier_order: t.tier_order,
          description: t.description || undefined,
          multiplier: t.multiplier,
          interest_ranges: t.interest_ranges.map(r => ({
            term_months: r.term_months || undefined,
            effective_rate_percent: r.effective_rate_percent
          }))
        }))
      } : undefined
    };

    try {
      let response;
      if (editingCycleId) {
        // Update existing cycle - use update request format
        const updateData = {
          cycle: {
            year,
            start_date: startDate,
            status: undefined, // Don't change status via edit form
            social_fund_required: socialFundRequired && socialFundRequired.trim() !== '' ? parseFloat(socialFundRequired) : null,
            admin_fund_required: adminFundRequired && adminFundRequired.trim() !== '' ? parseFloat(adminFundRequired) : null
          },
          phase_configs: cycleData.phase_configs,
          credit_rating_scheme: cycleData.credit_rating_scheme
        };
        response = await api.put(`/api/chairman/cycles/${editingCycleId}`, updateData);
        if (response.data) {
          setSuccess('Cycle updated successfully!');
        } else {
          setError(response.error || 'Failed to update cycle');
          return;
        }
      } else {
        // Create new cycle
        response = await api.post('/api/chairman/cycles', cycleData);
        if (response.data) {
          setSuccess('Cycle created successfully!');
        } else {
          setError(response.error || 'Failed to create cycle');
          return;
        }
      }
      
      setShowCreateForm(false);
      resetForm();
      loadCycles();
    } catch (err) {
      setError(editingCycleId ? 'Error updating cycle' : 'Error creating cycle');
    }
  };

  const handleActivate = async (cycleId: string) => {
    setActivating(cycleId);
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/chairman/cycles/${cycleId}/activate`);
      if (!response.error) {
        setSuccess(response.data?.message || 'Cycle activated successfully! All other cycles have been deactivated.');
        await loadCycles();
      } else {
        setError(response.error || 'Failed to activate cycle');
      }
    } catch (err) {
      setError('Error activating cycle');
    } finally {
      setActivating(null);
    }
  };

  const handleClose = async (cycleId: string) => {
    if (!confirm('Are you sure you want to close this cycle? This will prevent new declarations and loan applications for this cycle.')) {
      return;
    }
    
    setClosing(cycleId);
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/chairman/cycles/${cycleId}/close`);
      if (!response.error) {
        setSuccess(response.data?.message || 'Cycle closed successfully! All phases have been closed.');
        await loadCycles();
      } else {
        setError(response.error || 'Failed to close cycle');
      }
    } catch (err) {
      setError('Error closing cycle');
    } finally {
      setClosing(null);
    }
  };

  const handleReopen = async (cycleId: string) => {
    setReopening(cycleId);
    setError('');
    setSuccess('');
    try {
      const response = await api.put(`/api/chairman/cycles/${cycleId}/reopen`);
      if (!response.error) {
        setSuccess(response.data?.message || 'Cycle reopened successfully! You can now activate it if needed.');
        await loadCycles();
      } else {
        setError(response.error || 'Failed to reopen cycle');
      }
    } catch (err) {
      setError('Error reopening cycle');
    } finally {
      setReopening(null);
    }
  };

  const canActivateOrReopen = (cycle: Cycle): boolean => {
    // Check if cycle is from current year or future
    const currentYear = new Date().getFullYear();
    try {
      const cycleYear = parseInt(cycle.year);
      return cycleYear >= currentYear;
    } catch {
      // If year is not a number, allow (might be a string like "2024-2025")
      return true;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Manage Cycles</h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <button
                onClick={() => {
                  if (showCreateForm) {
                    setShowCreateForm(false);
                    resetForm();
                  } else {
                    setShowCreateForm(true);
                  }
                }}
                className="btn-primary"
              >
                {showCreateForm ? 'Cancel' : '+ New Cycle'}
              </button>
              <UserMenu />
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
            {success}
          </div>
        )}

        {showCreateForm && (
          <div className="card mb-6">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">
              {editingCycleId ? 'Edit Cycle' : 'Create New Cycle'}
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Cycle Basic Info */}
              <div className="border-b-2 border-blue-200 pb-4">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Cycle Information</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                  <div>
                    <label htmlFor="year" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Year *
                    </label>
                    <input
                      type="text"
                      id="year"
                      value={year}
                      onChange={(e) => setYear(e.target.value)}
                      required
                      className="w-full"
                      placeholder="e.g., 2024"
                    />
                  </div>
                  <div>
                    <label htmlFor="startDate" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Start Date *
                    </label>
                    <input
                      type="date"
                      id="startDate"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      required
                      className="w-full"
                    />
                    <p className="mt-2 text-sm text-blue-700">End date will be calculated as 1 year from start date</p>
                  </div>
                  <div>
                    <label htmlFor="social_fund_required" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Social Fund Required (Annual)
                    </label>
                    <input
                      type="number"
                      id="social_fund_required"
                      name="social_fund_required"
                      value={socialFundRequired}
                      onChange={(e) => setSocialFundRequired(e.target.value)}
                      min="0"
                      step="0.01"
                      placeholder="e.g., 100.00"
                      className="w-full"
                    />
                    <p className="mt-2 text-sm text-blue-700">Annual social fund requirement per member for this cycle</p>
                  </div>
                  <div>
                    <label htmlFor="admin_fund_required" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Admin Fund Required (Annual)
                    </label>
                    <input
                      type="number"
                      id="admin_fund_required"
                      name="admin_fund_required"
                      value={adminFundRequired}
                      onChange={(e) => setAdminFundRequired(e.target.value)}
                      min="0"
                      step="0.01"
                      placeholder="e.g., 50.00"
                      className="w-full"
                    />
                    <p className="mt-2 text-sm text-blue-700">Annual admin fund requirement per member for this cycle</p>
                  </div>
                </div>
              </div>

              {/* Phase Configuration */}
              <div className="border-b-2 border-blue-200 pb-4">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Monthly Phase Start Days</h3>
                <p className="text-sm md:text-base text-blue-700 mb-4">
                  Configure the day of month (1-31) when each phase starts. If a month doesn't have that day, it will use the last day of the month.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
                  <div>
                    <label htmlFor="declarationDay" className="block text-base font-semibold text-blue-900 mb-2">
                      Declaration Start Day *
                    </label>
                    <input
                      type="number"
                      id="declarationDay"
                      min="1"
                      max="31"
                      value={declarationStartDay}
                      onChange={(e) => setDeclarationStartDay(parseInt(e.target.value) || 1)}
                      required
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label htmlFor="loanApplicationDay" className="block text-base font-semibold text-blue-900 mb-2">
                      Loan Application Start Day *
                    </label>
                    <input
                      type="number"
                      id="loanApplicationDay"
                      min="1"
                      max="31"
                      value={loanApplicationStartDay}
                      onChange={(e) => setLoanApplicationStartDay(parseInt(e.target.value) || 1)}
                      required
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label htmlFor="depositsDay" className="block text-base font-semibold text-blue-900 mb-2">
                      Deposits Start Day *
                    </label>
                    <input
                      type="number"
                      id="depositsDay"
                      min="1"
                      max="31"
                      value={depositsStartDay}
                      onChange={(e) => setDepositsStartDay(parseInt(e.target.value) || 1)}
                      required
                      className="w-full"
                    />
                  </div>
                </div>
              </div>

              {/* Credit Rating Scheme */}
              <div>
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Credit Rating Scheme (Optional)</h3>
                <div className="space-y-4 mb-4">
                  <div>
                    <label htmlFor="schemeName" className="block text-base font-semibold text-blue-900 mb-2">
                      Scheme Name
                    </label>
                    <input
                      type="text"
                      id="schemeName"
                      value={schemeName}
                      onChange={(e) => setSchemeName(e.target.value)}
                      className="w-full"
                      placeholder="e.g., 2024 Credit Rating Scheme"
                    />
                  </div>
                  <div>
                    <label htmlFor="schemeDescription" className="block text-base font-semibold text-blue-900 mb-2">
                      Description
                    </label>
                    <textarea
                      id="schemeDescription"
                      value={schemeDescription}
                      onChange={(e) => setSchemeDescription(e.target.value)}
                      className="w-full"
                      rows={3}
                      placeholder="Optional description"
                    />
                  </div>
                </div>

                {schemeName && (
                  <div className="space-y-6">
                    <div className="flex justify-between items-center">
                      <h4 className="text-base md:text-lg font-semibold text-blue-900">Credit Rating Tiers</h4>
                      <button
                        type="button"
                        onClick={handleAddTier}
                        className="btn-secondary text-sm"
                      >
                        + Add Tier
                      </button>
                    </div>

                    {tiers.map((tier, tierIndex) => (
                      <div key={tierIndex} className="p-4 md:p-5 bg-blue-50 border-2 border-blue-200 rounded-xl space-y-4">
                        <div className="flex justify-between items-start">
                          <h5 className="text-base font-bold text-blue-900">Tier {tierIndex + 1}</h5>
                          {tiers.length > 1 && (
                            <button
                              type="button"
                              onClick={() => handleRemoveTier(tierIndex)}
                              className="text-red-600 hover:text-red-800 text-sm font-medium"
                            >
                              Remove
                            </button>
                          )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-semibold text-blue-900 mb-1">
                              Tier Name *
                            </label>
                            <input
                              type="text"
                              value={tier.tier_name}
                              onChange={(e) => handleUpdateTier(tierIndex, 'tier_name', e.target.value)}
                              required
                              className="w-full"
                              placeholder="e.g., LOW RISK"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-semibold text-blue-900 mb-1">
                              Tier Order *
                            </label>
                            <input
                              type="number"
                              value={tier.tier_order}
                              onChange={(e) => handleUpdateTier(tierIndex, 'tier_order', parseInt(e.target.value) || 1)}
                              required
                              min="1"
                              className="w-full"
                            />
                            <p className="text-xs text-blue-700 mt-1">Lower = better rating</p>
                          </div>
                          <div>
                            <label className="block text-sm font-semibold text-blue-900 mb-1">
                              Description
                            </label>
                            <input
                              type="text"
                              value={tier.description || ''}
                              onChange={(e) => handleUpdateTier(tierIndex, 'description', e.target.value)}
                              className="w-full"
                              placeholder="Optional description"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-semibold text-blue-900 mb-1">
                              Borrowing Multiplier *
                            </label>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={tier.multiplier}
                              onChange={(e) => handleUpdateTier(tierIndex, 'multiplier', parseFloat(e.target.value) || 0)}
                              required
                              className="w-full"
                              placeholder="e.g., 2.00 for 2× savings"
                            />
                          </div>
                        </div>

                        {/* Interest Rate Ranges */}
                        <div className="mt-4">
                          <div className="flex justify-between items-center mb-2">
                            <label className="block text-sm font-semibold text-blue-900">
                              Interest Rate Ranges
                            </label>
                            <button
                              type="button"
                              onClick={() => handleAddInterestRange(tierIndex)}
                              className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                            >
                              + Add Range
                            </button>
                          </div>
                          {tier.interest_ranges.map((range, rangeIndex) => (
                            <div key={rangeIndex} className="p-3 bg-white border border-blue-300 rounded-lg mb-2">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <div>
                                  <label className="block text-xs font-semibold text-blue-900 mb-1">
                                    Term (months)
                                  </label>
                                  <select
                                    value={range.term_months || ''}
                                    onChange={(e) => handleUpdateInterestRange(tierIndex, rangeIndex, 'term_months', e.target.value || null)}
                                    className="w-full text-sm"
                                  >
                                    <option value="">All Terms</option>
                                    <option value="1">1 Month</option>
                                    <option value="2">2 Months</option>
                                    <option value="3">3 Months</option>
                                    <option value="4">4 Months</option>
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs font-semibold text-blue-900 mb-1">
                                    Effective Rate (%)
                                  </label>
                                  <div className="flex gap-2">
                                    <input
                                      type="number"
                                      step="0.01"
                                      min="0"
                                      max="100"
                                      value={range.effective_rate_percent}
                                      onChange={(e) => handleUpdateInterestRange(tierIndex, rangeIndex, 'effective_rate_percent', parseFloat(e.target.value) || 0)}
                                      required
                                      className="w-full text-sm"
                                    />
                                    {tier.interest_ranges.length > 1 && (
                                      <button
                                        type="button"
                                        onClick={() => handleRemoveInterestRange(tierIndex, rangeIndex)}
                                        className="text-red-600 hover:text-red-800 text-sm px-2"
                                      >
                                        ×
                                      </button>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex flex-col sm:flex-row justify-end gap-3 md:gap-4 pt-6 border-t-2 border-blue-200">
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="btn-secondary text-center"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                >
                  {editingCycleId ? 'Update Cycle' : 'Create Cycle'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Existing Cycles List */}
        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Existing Cycles</h2>
          
          {/* Workflow Information Message */}
          <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 md:p-5 mb-6 text-sm md:text-base text-blue-800">
            <p className="font-semibold mb-2 text-base md:text-lg">Cycle Management Workflow:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>New cycles are created as <strong>DRAFT</strong> - they are not automatically activated</li>
              <li>Click <strong>Activate</strong> to make a cycle active (automatically deactivates other active cycles)</li>
              <li>Click <strong>Close Cycle</strong> when a cycle ends (can be reopened if needed)</li>
              <li>Click <strong>Reopen</strong> to change a closed cycle back to DRAFT status</li>
              <li>Only one cycle can be <strong>ACTIVE</strong> at a time</li>
              <li>Cycles from previous years cannot be activated or reopened</li>
            </ul>
          </div>
          
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading...</p>
            </div>
          ) : cycles.length === 0 ? (
            <p className="text-blue-700 text-lg text-center py-8">No cycles created yet</p>
          ) : (
            <div className="space-y-4">
              {cycles.map((cycle) => (
                <div
                  key={cycle.id}
                  className={`p-4 md:p-5 bg-gradient-to-r rounded-xl border-2 ${
                    cycle.status === 'active'
                      ? 'from-green-50 to-green-100 border-green-400'
                      : cycle.status === 'closed'
                      ? 'from-gray-50 to-gray-100 border-gray-400'
                      : 'from-blue-50 to-blue-100 border-blue-300'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="text-lg md:text-xl font-bold text-blue-900">
                          {cycle.year} Cycle
                        </h3>
                        {cycle.status === 'active' && (
                          <span className="px-3 py-1 bg-green-500 text-white text-xs font-bold rounded-full">
                            ACTIVE
                          </span>
                        )}
                        {cycle.status === 'closed' && (
                          <span className="px-3 py-1 bg-gray-500 text-white text-xs font-bold rounded-full">
                            CLOSED
                          </span>
                        )}
                        {cycle.status === 'draft' && (
                          <span className="px-3 py-1 bg-blue-500 text-white text-xs font-bold rounded-full">
                            DRAFT
                          </span>
                        )}
                      </div>
                      <p className="text-sm md:text-base text-blue-700">
                        {new Date(cycle.start_date).toLocaleDateString()} - {new Date(cycle.end_date).toLocaleDateString()}
                      </p>
                      <p className="text-sm text-blue-600 mt-1">
                        Status: <span className="font-semibold">{cycle.status.toUpperCase()}</span>
                      </p>
                      {cycle.phases && cycle.phases.length > 0 && (
                        <div className="mt-2 text-sm text-blue-700">
                          <p className="font-semibold">Phase Start Days:</p>
                          <ul className="list-disc list-inside ml-2">
                            {cycle.phases.map((phase) => (
                              <li key={phase.id}>
                                {phase.phase_type.replace('_', ' ')}: Day {phase.monthly_start_day || 'N/A'}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {cycle.credit_rating_scheme && (
                        <div className="mt-2 text-sm text-blue-700">
                          <p className="font-semibold">Credit Rating Scheme: {cycle.credit_rating_scheme.name}</p>
                          <p className="text-xs">Tiers: {cycle.credit_rating_scheme.tiers.length}</p>
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2">
                      {cycle.status !== 'closed' && (
                        <button
                          onClick={() => loadCycleForEdit(cycle.id)}
                          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                        >
                          Edit
                        </button>
                      )}
                      {cycle.status === 'active' && (
                        <button
                          onClick={() => handleClose(cycle.id)}
                          disabled={closing === cycle.id}
                          className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                        >
                          {closing === cycle.id ? 'Closing...' : 'Close Cycle'}
                        </button>
                      )}
                      {cycle.status === 'closed' && canActivateOrReopen(cycle) && (
                        <button
                          onClick={() => handleReopen(cycle.id)}
                          disabled={reopening === cycle.id}
                          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                        >
                          {reopening === cycle.id ? 'Reopening...' : 'Reopen'}
                        </button>
                      )}
                      {cycle.status === 'closed' && !canActivateOrReopen(cycle) && (
                        <span className="px-4 py-2 bg-gray-300 text-gray-600 rounded-lg text-sm font-semibold cursor-not-allowed">
                          Cannot reopen (previous year)
                        </span>
                      )}
                      {cycle.status !== 'active' && cycle.status !== 'closed' && canActivateOrReopen(cycle) && (
                        <button
                          onClick={() => handleActivate(cycle.id)}
                          disabled={activating === cycle.id}
                          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                        >
                          {activating === cycle.id ? 'Activating...' : 'Activate'}
                        </button>
                      )}
                      {cycle.status !== 'active' && cycle.status !== 'closed' && !canActivateOrReopen(cycle) && (
                        <span className="px-4 py-2 bg-gray-300 text-gray-600 rounded-lg text-sm font-semibold cursor-not-allowed">
                          Cannot activate (previous year)
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
