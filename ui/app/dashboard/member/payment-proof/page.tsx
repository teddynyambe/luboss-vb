'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { memberApi, DepositProof } from '@/lib/memberApi';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FaInfoCircle, FaCheckCircle, FaTimesCircle, FaComment, FaChevronDown, FaChevronUp, FaUpload, FaList } from 'react-icons/fa';
import UserMenu from '@/components/UserMenu';

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
}

export default function PaymentProofPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'upload' | 'view'>('upload');
  
  // Upload state
  const [declarations, setDeclarations] = useState<Declaration[]>([]);
  const [selectedDeclaration, setSelectedDeclaration] = useState<string>('');
  const [amount, setAmount] = useState<string>('');
  const [reference, setReference] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState(false);
  
  // View state
  const [deposits, setDeposits] = useState<DepositProof[]>([]);
  const [viewLoading, setViewLoading] = useState(true);
  const [viewError, setViewError] = useState('');
  const [selectedDepositForProof, setSelectedDepositForProof] = useState<DepositProof | null>(null);
  const [selectedDeposit, setSelectedDeposit] = useState<DepositProof | null>(null);
  const [showResponseModal, setShowResponseModal] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [submittingResponse, setSubmittingResponse] = useState(false);
  const [showProofModal, setShowProofModal] = useState(false);
  const [proofBlobUrl, setProofBlobUrl] = useState<string | null>(null);
  const [proofLoading, setProofLoading] = useState(false);
  const [proofError, setProofError] = useState<string | null>(null);
  const [expandedDeposits, setExpandedDeposits] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (activeTab === 'upload') {
      loadDeclarations();
    } else {
      loadDeposits();
    }
  }, [activeTab]);

  // Auto-expand active deposits on initial load
  useEffect(() => {
    if (deposits.length > 0 && expandedDeposits.size === 0) {
      const activeDepositIds = deposits
        .filter(d => d.status === 'submitted' || d.status === 'rejected')
        .map(d => d.id);
      if (activeDepositIds.length > 0) {
        setExpandedDeposits(new Set(activeDepositIds));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deposits.length]);

  const loadDeclarations = async () => {
    try {
      const response = await memberApi.getDeclarations();
      if (response.data) {
        const declarations = Array.isArray(response.data) ? response.data : [];
        const pending = declarations.filter(d => d.status === 'pending');
        setDeclarations(pending);
      }
    } catch (err) {
      console.error('Error loading declarations:', err);
      setUploadError('Failed to load declarations');
    }
  };

  const loadDeposits = async () => {
    setViewLoading(true);
    setViewError('');
    try {
      const response = await memberApi.getDepositProofs();
      if (response.data) {
        setDeposits(response.data);
      } else {
        setViewError(response.error || 'Failed to load deposit proofs');
      }
    } catch (err: any) {
      console.error('Error loading deposit proofs:', err);
      setViewError(err.message || 'Failed to load deposit proofs');
    } finally {
      setViewLoading(false);
    }
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

  const formatDate = (dateString: string) => {
    // Parse date string (YYYY-MM-DD) without timezone conversion
    const [year, month, day] = dateString.split('-').map(Number);
    const date = new Date(year, month - 1, day); // month is 0-indexed
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const calculateTotal = (declaration: Declaration): number => {
    return (
      (declaration.declared_savings_amount || 0) +
      (declaration.declared_social_fund || 0) +
      (declaration.declared_admin_fund || 0) +
      (declaration.declared_penalties || 0) +
      (declaration.declared_interest_on_loan || 0) +
      (declaration.declared_loan_repayment || 0)
    );
  };

  const handleDeclarationChange = (declarationId: string) => {
    setSelectedDeclaration(declarationId);
    const declaration = declarations.find(d => d.id === declarationId);
    if (declaration) {
      const total = calculateTotal(declaration);
      setAmount(total.toFixed(2));
    } else {
      setAmount('');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploadError('');
    setUploadSuccess(false);
    setUploadLoading(true);

    if (!selectedDeclaration) {
      setUploadError('Please select a declaration');
      setUploadLoading(false);
      return;
    }

    if (!amount || parseFloat(amount) <= 0) {
      setUploadError('Please enter a valid amount');
      setUploadLoading(false);
      return;
    }

    if (!file) {
      setUploadError('Please select a file to upload');
      setUploadLoading(false);
      return;
    }

    const declaration = declarations.find(d => d.id === selectedDeclaration);
    if (declaration) {
      const expectedTotal = calculateTotal(declaration);
      const enteredAmount = parseFloat(amount);
      if (Math.abs(enteredAmount - expectedTotal) > 0.01) {
        setUploadError(`Amount must match declaration total: K${expectedTotal.toFixed(2)}`);
        setUploadLoading(false);
        return;
      }
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('declaration_id', selectedDeclaration);
      formData.append('amount', amount);
      if (reference) {
        formData.append('reference', reference);
      }

      const response = await api.postFormData('/api/member/deposits/upload', formData);

      if (response.data) {
        setUploadSuccess(true);
        // Reset form
        setSelectedDeclaration('');
        setAmount('');
        setReference('');
        setFile(null);
        // Reload declarations
        await loadDeclarations();
        // Switch to view tab after 2 seconds
        setTimeout(() => {
          setActiveTab('view');
          loadDeposits();
        }, 2000);
      } else {
        setUploadError(response.error || 'Failed to upload deposit proof');
      }
    } catch (err: any) {
      setUploadError(err.message || 'An error occurred while uploading the proof');
    } finally {
      setUploadLoading(false);
    }
  };

  const toggleExpand = (depositId: string) => {
    setExpandedDeposits(prev => {
      const newSet = new Set(prev);
      if (newSet.has(depositId)) {
        newSet.delete(depositId);
      } else {
        newSet.add(depositId);
      }
      return newSet;
    });
  };

  const handleRespond = (deposit: DepositProof) => {
    setSelectedDeposit(deposit);
    setResponseText('');
    setShowResponseModal(true);
  };

  const handleSubmitResponse = async () => {
    if (!selectedDeposit || !responseText.trim()) {
      return;
    }

    setSubmittingResponse(true);
    try {
      const response = await memberApi.respondToDepositProof(selectedDeposit.id, responseText);
      if (response.data) {
        setShowResponseModal(false);
        setSelectedDeposit(null);
        setResponseText('');
        await loadDeposits();
      } else {
        setViewError(response.error || 'Failed to submit response');
      }
    } catch (err: any) {
      setViewError(err.message || 'Failed to submit response');
    } finally {
      setSubmittingResponse(false);
    }
  };

  const handleViewProof = async (deposit: DepositProof) => {
    setSelectedDepositForProof(deposit);
    setShowProofModal(true);
    setProofLoading(true);
    setProofError(null);
    setProofBlobUrl(null);

    try {
      const filename = deposit.upload_path.split('/').pop() || deposit.upload_path;
      const blobUrl = await api.getFileBlob(`/api/treasurer/deposits/proof/${encodeURIComponent(filename)}`);
      setProofBlobUrl(blobUrl);
    } catch (err: any) {
      setProofError(err.message || 'Failed to load proof');
    } finally {
      setProofLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'submitted':
        return <span className="px-3 py-1 bg-yellow-200 text-yellow-800 rounded-full text-xs font-semibold">Submitted</span>;
      case 'approved':
        return <span className="px-3 py-1 bg-green-200 text-green-800 rounded-full text-xs font-semibold">Approved</span>;
      case 'rejected':
        return <span className="px-3 py-1 bg-red-200 text-red-800 rounded-full text-xs font-semibold">Rejected</span>;
      default:
        return <span className="px-3 py-1 bg-gray-200 text-gray-800 rounded-full text-xs font-semibold">{status}</span>;
    }
  };

  const selectedDecl = declarations.find(d => d.id === selectedDeclaration);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Payment Proof</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="card">
          {/* Tab Navigation */}
          <div className="flex space-x-2 border-b-2 border-blue-200 mb-6">
            <button
              onClick={() => setActiveTab('upload')}
              className={`flex items-center space-x-2 px-4 py-2 font-semibold transition-colors ${
                activeTab === 'upload'
                  ? 'text-blue-900 border-b-2 border-blue-600'
                  : 'text-blue-600 hover:text-blue-800'
              }`}
            >
              <FaUpload />
              <span>Upload Proof</span>
            </button>
            <button
              onClick={() => setActiveTab('view')}
              className={`flex items-center space-x-2 px-4 py-2 font-semibold transition-colors ${
                activeTab === 'view'
                  ? 'text-blue-900 border-b-2 border-blue-600'
                  : 'text-blue-600 hover:text-blue-800'
              }`}
            >
              <FaList />
              <span>View Proofs</span>
            </button>
          </div>

          {/* Upload Tab */}
          {activeTab === 'upload' && (
            <>
              {uploadSuccess && (
                <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                  ✓ Deposit proof uploaded successfully! Declaration status updated to PROOF. Awaiting treasurer approval. Redirecting to view...
                </div>
              )}

              {uploadError && (
                <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                  {uploadError}
                </div>
              )}

              {declarations.length === 0 ? (
                <div className="text-center py-12">
                  <div className="mb-6">
                    <svg className="mx-auto h-24 w-24 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4">No Pending Declarations</h2>
                  <p className="text-lg md:text-xl text-blue-700 mb-6">
                    You don't have any pending declarations that require deposit proof.
                  </p>
                  <Link
                    href="/dashboard/member/declarations"
                    className="btn-primary inline-block"
                  >
                    Create Declaration
                  </Link>
                </div>
              ) : (
                <form onSubmit={handleUploadSubmit} className="space-y-4 md:space-y-6">
                  <div>
                    <label htmlFor="declaration_id" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Select Declaration *
                    </label>
                    <select
                      id="declaration_id"
                      value={selectedDeclaration}
                      onChange={(e) => handleDeclarationChange(e.target.value)}
                      required
                      className="w-full"
                    >
                      <option value="">-- Select a declaration --</option>
                      {declarations.map((decl) => (
                        <option key={decl.id} value={decl.id}>
                          {formatMonth(decl.effective_month)} - 
                          Total: K{calculateTotal(decl).toFixed(2)}
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedDecl && (
                    <div className="bg-blue-50 border-2 border-blue-300 rounded-xl p-4 md:p-5">
                      <h3 className="text-lg font-bold text-blue-900 mb-3">Declaration Breakdown</h3>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
                        {selectedDecl.declared_savings_amount !== null && selectedDecl.declared_savings_amount !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Savings</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_savings_amount.toLocaleString()}</p>
                          </div>
                        )}
                        {selectedDecl.declared_social_fund !== null && selectedDecl.declared_social_fund !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Social Fund</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_social_fund.toLocaleString()}</p>
                          </div>
                        )}
                        {selectedDecl.declared_admin_fund !== null && selectedDecl.declared_admin_fund !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Admin Fund</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_admin_fund.toLocaleString()}</p>
                          </div>
                        )}
                        {selectedDecl.declared_penalties !== null && selectedDecl.declared_penalties !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Penalties</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_penalties.toLocaleString()}</p>
                          </div>
                        )}
                        {selectedDecl.declared_interest_on_loan !== null && selectedDecl.declared_interest_on_loan !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Interest on Loan</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_interest_on_loan.toLocaleString()}</p>
                          </div>
                        )}
                        {selectedDecl.declared_loan_repayment !== null && selectedDecl.declared_loan_repayment !== undefined && (
                          <div>
                            <p className="text-xs text-blue-600 font-medium">Loan Repayment</p>
                            <p className="text-base font-bold text-blue-900">K{selectedDecl.declared_loan_repayment.toLocaleString()}</p>
                          </div>
                        )}
                      </div>
                      <div className="mt-4 pt-4 border-t-2 border-blue-200">
                        <p className="text-sm text-blue-600 font-medium">Total Amount</p>
                        <p className="text-2xl font-bold text-blue-900">K{calculateTotal(selectedDecl).toFixed(2)}</p>
                      </div>
                    </div>
                  )}

                  <div>
                    <label htmlFor="amount" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Deposit Amount (K) *
                    </label>
                    <input
                      type="number"
                      id="amount"
                      step="0.01"
                      min="0"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      required
                      className="w-full"
                      placeholder="0.00"
                    />
                    <p className="mt-2 text-sm md:text-base text-blue-700">
                      This should match the total from your declaration
                    </p>
                  </div>

                  <div>
                    <label htmlFor="reference" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Payment Reference (Optional)
                    </label>
                    <input
                      type="text"
                      id="reference"
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                      className="w-full"
                      placeholder="e.g., Transaction ID, Reference Number"
                    />
                  </div>

                  <div>
                    <label htmlFor="file" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                      Upload Proof of Payment *
                    </label>
                    <input
                      type="file"
                      id="file"
                      accept=".pdf,.jpg,.jpeg,.png,.gif"
                      onChange={handleFileChange}
                      required
                      className="w-full"
                    />
                    <p className="mt-2 text-sm md:text-base text-blue-700">
                      Accepted formats: PDF, JPG, JPEG, PNG, GIF
                    </p>
                    {file && (
                      <p className="mt-2 text-sm text-green-700 font-medium">
                        Selected: {file.name} ({(file.size / 1024).toFixed(2)} KB)
                      </p>
                    )}
                  </div>

                  <div className="flex flex-col sm:flex-row justify-end gap-3 md:gap-4 pt-6 border-t-2 border-blue-200">
                    <Link
                      href="/dashboard/member"
                      className="btn-secondary text-center"
                    >
                      Cancel
                    </Link>
                    <button
                      type="submit"
                      disabled={uploadLoading}
                      className="btn-primary disabled:opacity-50"
                    >
                      {uploadLoading ? 'Uploading...' : 'Upload Proof'}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}

          {/* View Tab */}
          {activeTab === 'view' && (
            <>
              {viewError && (
                <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
                  {viewError}
                </div>
              )}

              {viewLoading ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                  <p className="mt-4 text-blue-700 text-lg">Loading deposit proofs...</p>
                </div>
              ) : deposits.length === 0 ? (
                <div className="text-center py-12">
                  <div className="mb-6">
                    <svg className="mx-auto h-24 w-24 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h2 className="text-2xl md:text-3xl font-bold text-blue-900 mb-4">No Deposit Proofs</h2>
                  <p className="text-lg md:text-xl text-blue-700 mb-6">
                    You haven't uploaded any deposit proofs yet.
                  </p>
                  <button
                    onClick={() => setActiveTab('upload')}
                    className="btn-primary inline-block"
                  >
                    Upload Deposit Proof
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {deposits.map((deposit) => (
                    <div
                      key={deposit.id}
                      className="bg-white border-2 border-blue-200 rounded-xl p-4 md:p-5 hover:shadow-lg transition-shadow"
                    >
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="text-lg md:text-xl font-bold text-blue-900">
                              {deposit.effective_month ? formatMonth(deposit.effective_month) : 'Deposit Proof'}
                            </h3>
                            {getStatusBadge(deposit.status)}
                          </div>
                          <div className="text-sm text-blue-600 space-y-1">
                            <p>Amount: K{parseFloat(String(deposit.amount)).toLocaleString()}</p>
                            <p>Uploaded: {formatDate(deposit.uploaded_at)}</p>
                            {deposit.reference && <p>Reference: {deposit.reference}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleViewProof(deposit)}
                            className="px-3 py-1 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 text-sm font-medium"
                          >
                            View Proof
                          </button>
                          <button
                            onClick={() => toggleExpand(deposit.id)}
                            className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                          >
                            {expandedDeposits.has(deposit.id) ? <FaChevronUp /> : <FaChevronDown />}
                          </button>
                        </div>
                      </div>

                      {expandedDeposits.has(deposit.id) && (
                        <div className="mt-4 pt-4 border-t-2 border-blue-200">
                          {deposit.status === 'rejected' && deposit.treasurer_comment && (
                            <div className="mb-4 p-3 bg-red-50 border-2 border-red-200 rounded-lg">
                              <div className="flex items-start gap-2">
                                <FaTimesCircle className="text-red-600 mt-1 flex-shrink-0" />
                                <div className="flex-1">
                                  <p className="font-semibold text-red-900 mb-1">Treasurer Comment:</p>
                                  <p className="text-sm text-red-800">{deposit.treasurer_comment}</p>
                                </div>
                              </div>
                            </div>
                          )}

                          {deposit.status === 'approved' && (
                            <div className="mb-4 p-3 bg-green-50 border-2 border-green-200 rounded-lg">
                              <div className="flex items-center gap-2">
                                <FaCheckCircle className="text-green-600" />
                                <p className="font-semibold text-green-900">Deposit approved</p>
                              </div>
                            </div>
                          )}

                          {deposit.status === 'rejected' && !deposit.member_response && (
                            <div className="mb-4">
                              <button
                                onClick={() => handleRespond(deposit)}
                                className="btn-primary"
                              >
                                Respond to Rejection
                              </button>
                            </div>
                          )}

                          {deposit.member_response && (
                            <div className="mb-4 p-3 bg-blue-50 border-2 border-blue-200 rounded-lg">
                              <div className="flex items-start gap-2">
                                <FaComment className="text-blue-600 mt-1 flex-shrink-0" />
                                <div className="flex-1">
                                  <p className="font-semibold text-blue-900 mb-1">Your Response:</p>
                                  <p className="text-sm text-blue-800">{deposit.member_response}</p>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {/* Response Modal */}
      {showResponseModal && selectedDeposit && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-md w-full">
            <h3 className="text-xl font-bold text-blue-900 mb-4">Respond to Rejection</h3>
            <textarea
              value={responseText}
              onChange={(e) => setResponseText(e.target.value)}
              placeholder="Enter your response..."
              className="w-full p-3 border-2 border-blue-200 rounded-lg mb-4"
              rows={4}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowResponseModal(false);
                  setSelectedDeposit(null);
                  setResponseText('');
                }}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitResponse}
                disabled={!responseText.trim() || submittingResponse}
                className="btn-primary disabled:opacity-50"
              >
                {submittingResponse ? 'Submitting...' : 'Submit Response'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Proof View Modal */}
      {showProofModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-4xl w-full max-h-[90vh] overflow-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold text-blue-900">Proof of Payment</h3>
              <button
                onClick={() => {
                  setShowProofModal(false);
                  if (proofBlobUrl) {
                    URL.revokeObjectURL(proofBlobUrl);
                    setProofBlobUrl(null);
                  }
                  setSelectedDepositForProof(null);
                }}
                className="text-blue-600 hover:text-blue-800 text-2xl"
              >
                ×
              </button>
            </div>
            {proofLoading && (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700">Loading proof...</p>
              </div>
            )}
            {proofError && (
              <div className="bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 rounded-xl">
                {proofError}
              </div>
            )}
            {proofBlobUrl && selectedDepositForProof && (
              <div className="mt-4">
                {selectedDepositForProof.upload_path.toLowerCase().endsWith('.pdf') ? (
                  <iframe src={proofBlobUrl} className="w-full h-[600px] border-2 border-blue-200 rounded-lg" />
                ) : (
                  <img src={proofBlobUrl} alt="Proof of payment" className="w-full h-auto border-2 border-blue-200 rounded-lg" />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
