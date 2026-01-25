'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { memberApi, Declaration } from '@/lib/memberApi';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

export default function DeclarationsListPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [declarations, setDeclarations] = useState<Declaration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    loadDeclarations();
  }, []);

  const loadDeclarations = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        setDeclarations(response.data);
      } else {
        setError(response.error || 'Failed to load declarations');
      }
    } catch (err) {
      console.error('Error loading declarations:', err);
      setError('An error occurred while loading declarations');
    } finally {
      setLoading(false);
    }
  };

  const [selectedDeclaration, setSelectedDeclaration] = useState<Declaration | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);

  const handleEdit = (declaration: Declaration) => {
    // Navigate to edit page with declaration ID
    if (declaration.can_edit) {
      router.push(`/dashboard/member/declarations?edit=${declaration.id}`);
    }
  };

  const handleView = (declaration: Declaration) => {
    setSelectedDeclaration(declaration);
    setShowDetailsModal(true);
  };

  const closeModal = () => {
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

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
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
    const datePart = dateString.split('T')[0].split(' ')[0]; // Get just the date part
    const [year, month] = datePart.split('-').map(Number);
    const now = new Date();
    return year === now.getFullYear() && month === now.getMonth() + 1; // month is 1-indexed in date string
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
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">My Declarations</h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link
                href="/dashboard/member/declarations"
                className="btn-primary"
              >
                + New Declaration
              </Link>
              <UserMenu />
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="card">
          {error && (
            <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading declarations...</p>
            </div>
          ) : declarations.length === 0 ? (
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
              <Link
                href="/dashboard/member/declarations"
                className="btn-primary inline-block"
              >
                Create Your First Declaration
              </Link>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                <h2 className="text-xl md:text-2xl font-bold text-blue-900">
                  All Declarations ({declarations.length})
                </h2>
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
                    {declarations.map((declaration) => {
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
                                  onClick={() => handleEdit(declaration)}
                                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                                >
                                  Edit
                                </button>
                              )}
                              {(isCurrent && !declaration.can_edit) || !isCurrent ? (
                                <button
                                  onClick={() => handleView(declaration)}
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

              {/* Summary Card */}
              <div className="mt-6 bg-blue-50 border-2 border-blue-300 rounded-xl p-4 md:p-5">
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-3">Summary</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-xs md:text-sm text-blue-600 font-medium">Total Declarations</p>
                    <p className="text-xl md:text-2xl font-bold text-blue-900">{declarations.length}</p>
                  </div>
                  <div>
                    <p className="text-xs md:text-sm text-blue-600 font-medium">Pending</p>
                    <p className="text-xl md:text-2xl font-bold text-yellow-700">
                      {declarations.filter(d => d.status === 'pending').length}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs md:text-sm text-blue-600 font-medium">Approved</p>
                    <p className="text-xl md:text-2xl font-bold text-green-700">
                      {declarations.filter(d => d.status === 'approved').length}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs md:text-sm text-blue-600 font-medium">Current Month</p>
                    <p className="text-xl md:text-2xl font-bold text-blue-700">
                      {declarations.filter(d => isCurrentMonth(d.effective_month)).length}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
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
                  onClick={closeModal}
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
                  onClick={closeModal}
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
