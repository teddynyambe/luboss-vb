'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';

interface PendingDeposit {
  id: string;
  amount: number;
  reference?: string;
  member_id: string;
  member_name: string;
  member_email?: string;
  declaration_id?: string;
  effective_month?: string;
  declared_savings_amount?: number;
  declared_social_fund?: number;
  declared_admin_fund?: number;
  declared_penalties?: number;
  declared_interest_on_loan?: number;
  declared_loan_repayment?: number;
  uploaded_at: string;
  upload_path: string;
  treasurer_comment?: string;
  member_response?: string;
  rejected_at?: string;
  status: string;
}

interface PendingPenalty {
  id: string;
  member_id: string;
  date_issued: string;
  penalty_type?: { name: string; fee_amount: string };
}

interface PendingLoanApplication {
  id: string;
  member_id: string;
  member_name: string;
  member_email?: string;
  amount: number;
  term_months: string;
  application_date: string;
  cycle_id: string;
  notes?: string;
}

interface ActiveLoan {
  id: string;
  member_id: string;
  member_name: string;
  member_email?: string;
  loan_amount: number;
  term_months: string;
  interest_rate?: number;
  disbursement_date?: string;
  total_principal_paid: number;
  total_interest_paid: number;
  total_paid: number;
  outstanding_balance: number;
  repayment_count: number;
}

interface LoanDetail {
  id: string;
  member_name: string;
  member_email?: string;
  loan_amount: number;
  term_months: string;
  interest_rate?: number;
  disbursement_date?: string;
  total_principal_paid: number;
  total_interest_paid: number;
  total_paid: number;
  outstanding_balance: number;
  payment_performance: string;
  all_payments_on_time: boolean;
  repayments: Array<{
    id: string;
    date: string;
    principal: number;
    interest: number;
    total: number;
    is_on_time: boolean;
  }>;
}


export default function TreasurerDashboard() {
  const [pendingDeposits, setPendingDeposits] = useState<PendingDeposit[]>([]);
  const [pendingPenalties, setPendingPenalties] = useState<PendingPenalty[]>([]);
  const [pendingLoans, setPendingLoans] = useState<PendingLoanApplication[]>([]);
  const [activeLoans, setActiveLoans] = useState<ActiveLoan[]>([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [approvingLoan, setApprovingLoan] = useState<string | null>(null);
  const [selectedLoan, setSelectedLoan] = useState<LoanDetail | null>(null);
  const [showLoanModal, setShowLoanModal] = useState(false);
  const [loadingLoanDetails, setLoadingLoanDetails] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [selectedDeposit, setSelectedDeposit] = useState<PendingDeposit | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showProofModal, setShowProofModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectComment, setRejectComment] = useState('');
  const [proofBlobUrl, setProofBlobUrl] = useState<string | null>(null);
  const [proofLoading, setProofLoading] = useState(false);
  const [proofError, setProofError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const [depositsRes, penaltiesRes, loansRes, activeLoansRes] = await Promise.all([
      api.get<PendingDeposit[]>('/api/treasurer/deposits/pending'),
      api.get<PendingPenalty[]>('/api/treasurer/penalties/pending'),
      api.get<PendingLoanApplication[]>('/api/treasurer/loans/pending'),
      api.get<ActiveLoan[]>('/api/treasurer/loans/active'),
    ]);

    if (depositsRes.data) setPendingDeposits(depositsRes.data);
    if (penaltiesRes.data) setPendingPenalties(penaltiesRes.data);
    if (loansRes.data) setPendingLoans(loansRes.data);
    if (activeLoansRes.data) setActiveLoans(activeLoansRes.data);
    setLoading(false);
  };

  const handleViewLoanDetails = async (loanId: string) => {
    setLoadingLoanDetails(true);
    setShowLoanModal(true);
    try {
      const response = await api.get<LoanDetail>(`/api/treasurer/loans/${loanId}/details`);
      if (response.data) {
        setSelectedLoan(response.data);
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to load loan details' });
        setShowLoanModal(false);
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error loading loan details' });
      setShowLoanModal(false);
    } finally {
      setLoadingLoanDetails(false);
    }
  };

  const closeLoanModal = () => {
    setShowLoanModal(false);
    setSelectedLoan(null);
  };

  const handleApproveDeposit = async (depositId: string) => {
    setApproving(depositId);
    setMessage(null);
    try {
      const response = await api.post(`/api/treasurer/deposits/${depositId}/approve`);
      if (!response.error) {
        setMessage({ type: 'success', text: 'Deposit approved and posted to ledger successfully!' });
        await loadData();
        if (showDetailsModal) {
          setShowDetailsModal(false);
        }
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to approve deposit' });
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error approving deposit' });
    } finally {
      setApproving(null);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  const handleRejectDeposit = async (depositId: string) => {
    if (!rejectComment.trim()) {
      setMessage({ type: 'error', text: 'Please provide a comment explaining why the deposit proof is being rejected.' });
      return;
    }
    
    setRejecting(depositId);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append('comment', rejectComment);
      const response = await api.postFormData(`/api/treasurer/deposits/${depositId}/reject`, formData);
      if (!response.error) {
        setMessage({ type: 'success', text: 'Deposit proof rejected. Member has been notified and can update their declaration.' });
        setRejectComment('');
        setShowRejectModal(false);
        await loadData();
        if (showDetailsModal) {
          setShowDetailsModal(false);
        }
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to reject deposit proof' });
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error rejecting deposit proof' });
    } finally {
      setRejecting(null);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  const handleApproveLoan = async (applicationId: string) => {
    if (!confirm('Are you sure you want to approve and disburse this loan? This will post it to the member\'s account and make it active.')) {
      return;
    }
    
    setApprovingLoan(applicationId);
    setMessage(null);
    try {
      const response = await api.post(`/api/treasurer/loans/${applicationId}/approve`);
      if (!response.error) {
        setMessage({ type: 'success', text: 'Loan approved, disbursed, and posted to member\'s account successfully!' });
        await loadData();
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to approve and disburse loan' });
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error approving and disbursing loan' });
    } finally {
      setApprovingLoan(null);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  const openRejectModal = (deposit: PendingDeposit) => {
    setSelectedDeposit(deposit);
    // Pre-fill comment if already rejected (for updating)
    setRejectComment(deposit.treasurer_comment || '');
    setShowRejectModal(true);
  };

  const handleViewDetails = (deposit: PendingDeposit) => {
    setSelectedDeposit(deposit);
    setShowDetailsModal(true);
  };

  const closeModal = () => {
    setShowDetailsModal(false);
    setSelectedDeposit(null);
  };

  const handleViewProof = async (uploadPath: string) => {
    setProofLoading(true);
    setProofError(null);
    setShowProofModal(true);
    
    try {
      // Extract filename from path
      const filename = uploadPath.split('/').pop() || uploadPath;
      // Fetch file as blob with authentication
      const blobUrl = await api.getFileBlob(`/api/treasurer/deposits/proof/${encodeURIComponent(filename)}`);
      setProofBlobUrl(blobUrl);
    } catch (error) {
      setProofError(error instanceof Error ? error.message : 'Failed to load proof file');
      setProofBlobUrl(null);
    } finally {
      setProofLoading(false);
    }
  };

  const closeProofModal = () => {
    setShowProofModal(false);
    if (proofBlobUrl) {
      URL.revokeObjectURL(proofBlobUrl);
      setProofBlobUrl(null);
    }
    setProofError(null);
  };

  const getFileExtension = (filename: string): string => {
    return filename.split('.').pop()?.toLowerCase() || '';
  };

  const isImage = (filename: string): boolean => {
    const ext = getFileExtension(filename);
    return ['jpg', 'jpeg', 'png', 'gif'].includes(ext);
  };

  const handleApprovePenalty = async (penaltyId: string) => {
    const response = await api.post(`/api/treasurer/penalties/${penaltyId}/approve`);
    if (!response.error) {
      alert('Penalty approved and posted successfully');
      loadData();
    } else {
      alert('Error: ' + response.error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Treasurer Dashboard</h1>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="space-y-4 md:space-y-6">
          {/* Pending Deposits */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Pending Deposit Proofs</h2>
            
            {message && (
              <div
                className={`mb-4 md:mb-6 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium ${
                  message.type === 'success'
                    ? 'bg-green-100 border-2 border-green-400 text-green-800'
                    : 'bg-red-100 border-2 border-red-400 text-red-800'
                }`}
              >
                {message.text}
              </div>
            )}

            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : pendingDeposits.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">No pending deposit proofs</p>
            ) : (
              <div className="space-y-3 md:space-y-4">
                {pendingDeposits.map((deposit) => (
                  <div
                    key={deposit.id}
                    className="p-4 md:p-5 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl"
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 md:gap-4 mb-3">
                      <div className="flex-1">
                        <p className="font-bold text-base md:text-lg text-blue-900">
                          {deposit.member_name} ({deposit.member_email})
                        </p>
                        <p className="text-sm md:text-base text-blue-700">
                          Amount: <span className="font-semibold">K{deposit.amount.toLocaleString()}</span>
                        </p>
                        {deposit.effective_month && (
                          <p className="text-sm text-blue-600">
                            Declaration Month: {new Date(deposit.effective_month).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}
                          </p>
                        )}
                        <p className="text-xs text-blue-600 mt-1">
                          Uploaded: {new Date(deposit.uploaded_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
                        <button
                          onClick={() => handleViewDetails(deposit)}
                          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm font-semibold transition-colors"
                        >
                          View Details
                        </button>
                        {deposit.status === 'submitted' && (
                          <>
                            <button
                              onClick={() => openRejectModal(deposit)}
                              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-semibold transition-colors"
                            >
                              Reject
                            </button>
                            <button
                              onClick={() => handleApproveDeposit(deposit.id)}
                              disabled={approving === deposit.id}
                              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                            >
                              {approving === deposit.id ? 'Approving...' : 'Approve & Post'}
                            </button>
                          </>
                        )}
                        {deposit.status === 'rejected' && (
                          <>
                            <button
                              onClick={() => openRejectModal(deposit)}
                              className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm font-semibold transition-colors"
                            >
                              Update Rejection
                            </button>
                            <button
                              onClick={() => handleApproveDeposit(deposit.id)}
                              disabled={approving === deposit.id}
                              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                            >
                              {approving === deposit.id ? 'Approving...' : 'Approve & Post'}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Pending Loan Applications */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Pending Loan Applications</h2>
            
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : pendingLoans.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">No pending loan applications</p>
            ) : (
              <div className="space-y-3 md:space-y-4">
                {pendingLoans.map((loan) => (
                  <div
                    key={loan.id}
                    className="p-4 md:p-5 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl"
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 md:gap-4">
                      <div className="flex-1">
                        <p className="font-bold text-base md:text-lg text-blue-900">
                          {loan.member_name} {loan.member_email && `(${loan.member_email})`}
                        </p>
                        <p className="text-sm md:text-base text-blue-700">
                          Loan Amount: <span className="font-semibold">K{loan.amount.toLocaleString()}</span>
                        </p>
                        <p className="text-sm md:text-base text-blue-700">
                          Term: <span className="font-semibold">{loan.term_months} {loan.term_months === '1' ? 'Month' : 'Months'}</span>
                        </p>
                        {loan.notes && (
                          <p className="text-sm text-blue-600 mt-2">
                            Notes: {loan.notes}
                          </p>
                        )}
                        <p className="text-xs text-blue-600 mt-1">
                          Applied: {new Date(loan.application_date).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
                        <button
                          onClick={() => handleApproveLoan(loan.id)}
                          disabled={approvingLoan === loan.id}
                          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                        >
                          {approvingLoan === loan.id ? 'Approving & Disbursing...' : 'Approve & Disburse'}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Loans */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Active Loans</h2>
            
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : activeLoans.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">No active loans</p>
            ) : (
              <div className="space-y-3 md:space-y-4">
                {activeLoans.map((loan) => (
                  <div
                    key={loan.id}
                    className="p-4 md:p-5 bg-gradient-to-r from-green-50 to-green-100 border-2 border-green-300 rounded-xl cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => handleViewLoanDetails(loan.id)}
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 md:gap-4">
                      <div className="flex-1">
                        <p className="font-bold text-base md:text-lg text-blue-900">
                          {loan.member_name} {loan.member_email && `(${loan.member_email})`}
                        </p>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4 mt-2">
                          <div>
                            <p className="text-xs md:text-sm text-blue-700">Loan Amount</p>
                            <p className="text-sm md:text-base font-semibold text-blue-900">K{loan.loan_amount.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700">Outstanding</p>
                            <p className="text-sm md:text-base font-semibold text-red-700">K{loan.outstanding_balance.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700">Total Paid</p>
                            <p className="text-sm md:text-base font-semibold text-green-700">K{loan.total_paid.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-xs md:text-sm text-blue-700">Repayments</p>
                            <p className="text-sm md:text-base font-semibold text-blue-900">{loan.repayment_count}</p>
                          </div>
                        </div>
                        {loan.disbursement_date && (
                          <p className="text-xs text-blue-600 mt-2">
                            Disbursed: {new Date(loan.disbursement_date).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                      <div className="text-blue-600 text-sm md:text-base font-medium">
                        Click to view details →
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Pending Penalties */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Pending Penalties</h2>
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : pendingPenalties.length === 0 ? (
              <p className="text-blue-700 text-lg text-center py-8">No pending penalties</p>
            ) : (
              <div className="space-y-3 md:space-y-4">
                {pendingPenalties.map((penalty) => (
                  <div
                    key={penalty.id}
                    className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 md:p-5 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-xl gap-3 md:gap-4"
                  >
                    <div>
                      <p className="font-bold text-base md:text-lg text-blue-900">
                        {penalty.penalty_type?.name || 'Penalty'}
                      </p>
                      <p className="text-sm md:text-base text-blue-700">
                        Fee: K{penalty.penalty_type?.fee_amount || '0.00'}
                      </p>
                    </div>
                    <button
                      onClick={() => handleApprovePenalty(penalty.id)}
                      className="btn-primary bg-gradient-to-br from-green-500 to-green-600 border-green-600 w-full sm:w-auto"
                    >
                      Approve
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Deposit Details Modal */}
      {showDetailsModal && selectedDeposit && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Deposit Proof Details</h2>
              <button
                onClick={closeModal}
                className="text-white hover:text-blue-200 text-2xl font-bold"
              >
                ×
              </button>
            </div>
            
            <div className="p-6 md:p-8 space-y-6">
              {/* Member Info */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-4 border-b-2 border-blue-200">
                <div>
                  <p className="text-sm text-blue-600 font-medium mb-1">Member</p>
                  <p className="text-lg font-bold text-blue-900">{selectedDeposit.member_name}</p>
                  <p className="text-sm text-blue-700">{selectedDeposit.member_email}</p>
                </div>
                <div>
                  <p className="text-sm text-blue-600 font-medium mb-1">Total Deposit Amount</p>
                  <p className="text-2xl font-bold text-blue-900">K{selectedDeposit.amount.toLocaleString()}</p>
                </div>
                {selectedDeposit.reference && (
                  <div>
                    <p className="text-sm text-blue-600 font-medium mb-1">Reference</p>
                    <p className="text-base text-blue-900">{selectedDeposit.reference}</p>
                  </div>
                )}
                {selectedDeposit.effective_month && (
                  <div>
                    <p className="text-sm text-blue-600 font-medium mb-1">Declaration Month</p>
                    <p className="text-base text-blue-900">
                      {new Date(selectedDeposit.effective_month).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}
                    </p>
                  </div>
                )}
              </div>

              {/* Declaration Breakdown */}
              <div>
                <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Declaration Breakdown</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {selectedDeposit.declared_savings_amount !== null && selectedDeposit.declared_savings_amount !== undefined && (
                    <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                      <p className="text-sm text-blue-600 font-medium mb-2">Savings</p>
                      <p className="text-xl font-bold text-blue-900">K{selectedDeposit.declared_savings_amount.toLocaleString()}</p>
                    </div>
                  )}
                  {selectedDeposit.declared_social_fund !== null && selectedDeposit.declared_social_fund !== undefined && (
                    <div className="bg-purple-50 border-2 border-purple-200 rounded-xl p-4">
                      <p className="text-sm text-purple-600 font-medium mb-2">Social Fund</p>
                      <p className="text-xl font-bold text-purple-900">K{selectedDeposit.declared_social_fund.toLocaleString()}</p>
                    </div>
                  )}
                  {selectedDeposit.declared_admin_fund !== null && selectedDeposit.declared_admin_fund !== undefined && (
                    <div className="bg-indigo-50 border-2 border-indigo-200 rounded-xl p-4">
                      <p className="text-sm text-indigo-600 font-medium mb-2">Admin Fund</p>
                      <p className="text-xl font-bold text-indigo-900">K{selectedDeposit.declared_admin_fund.toLocaleString()}</p>
                    </div>
                  )}
                  {selectedDeposit.declared_penalties !== null && selectedDeposit.declared_penalties !== undefined && (
                    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
                      <p className="text-sm text-yellow-600 font-medium mb-2">Penalties</p>
                      <p className="text-xl font-bold text-yellow-900">K{selectedDeposit.declared_penalties.toLocaleString()}</p>
                    </div>
                  )}
                  {selectedDeposit.declared_interest_on_loan !== null && selectedDeposit.declared_interest_on_loan !== undefined && (
                    <div className="bg-green-50 border-2 border-green-200 rounded-xl p-4">
                      <p className="text-sm text-green-600 font-medium mb-2">Interest on Loan</p>
                      <p className="text-xl font-bold text-green-900">K{selectedDeposit.declared_interest_on_loan.toLocaleString()}</p>
                    </div>
                  )}
                  {selectedDeposit.declared_loan_repayment !== null && selectedDeposit.declared_loan_repayment !== undefined && (
                    <div className="bg-red-50 border-2 border-red-200 rounded-xl p-4">
                      <p className="text-sm text-red-600 font-medium mb-2">Loan Repayment</p>
                      <p className="text-xl font-bold text-red-900">K{selectedDeposit.declared_loan_repayment.toLocaleString()}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Comments Section */}
              {selectedDeposit.treasurer_comment && (
                <div className="bg-yellow-50 border-2 border-yellow-300 rounded-xl p-4">
                  <h3 className="text-lg font-bold text-yellow-900 mb-2">Treasurer's Comment</h3>
                  <p className="text-base text-yellow-800 whitespace-pre-wrap">{selectedDeposit.treasurer_comment}</p>
                  {selectedDeposit.rejected_at && (
                    <p className="text-xs text-yellow-600 mt-2">
                      Rejected on: {new Date(selectedDeposit.rejected_at).toLocaleString()}
                    </p>
                  )}
                </div>
              )}

              {selectedDeposit.member_response && (
                <div className="bg-blue-50 border-2 border-blue-300 rounded-xl p-4">
                  <h3 className="text-lg font-bold text-blue-900 mb-2">Member's Response</h3>
                  <p className="text-base text-blue-800 whitespace-pre-wrap">{selectedDeposit.member_response}</p>
                </div>
              )}

              {/* Proof File */}
              <div className="bg-gray-50 border-2 border-gray-300 rounded-xl p-4">
                <h3 className="text-lg font-bold text-blue-900 mb-3">Proof of Payment</h3>
                <button
                  onClick={() => handleViewProof(selectedDeposit.upload_path)}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                >
                  View/Download Proof File
                </button>
              </div>

              {/* Footer */}
              <div className="flex justify-end gap-3 pt-4 border-t-2 border-blue-200">
                <button
                  onClick={closeModal}
                  className="btn-secondary"
                >
                  Close
                </button>
                {selectedDeposit.status === 'submitted' && (
                  <>
                    <button
                      onClick={() => {
                        closeModal();
                        openRejectModal(selectedDeposit);
                      }}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-semibold transition-colors"
                    >
                      Reject with Comment
                    </button>
                    <button
                      onClick={() => {
                        closeModal();
                        handleApproveDeposit(selectedDeposit.id);
                      }}
                      disabled={approving === selectedDeposit.id}
                      className="btn-primary bg-gradient-to-br from-green-500 to-green-600 border-green-600 disabled:opacity-50"
                    >
                      {approving === selectedDeposit.id ? 'Approving...' : 'Approve & Post to Ledger'}
                    </button>
                  </>
                )}
                {selectedDeposit.status === 'rejected' && (
                  <>
                    <button
                      onClick={() => {
                        closeModal();
                        openRejectModal(selectedDeposit);
                      }}
                      className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm font-semibold transition-colors"
                    >
                      Update Rejection Comment
                    </button>
                    <button
                      onClick={() => {
                        closeModal();
                        handleApproveDeposit(selectedDeposit.id);
                      }}
                      disabled={approving === selectedDeposit.id}
                      className="btn-primary bg-gradient-to-br from-green-500 to-green-600 border-green-600 disabled:opacity-50"
                    >
                      {approving === selectedDeposit.id ? 'Approving...' : 'Approve & Post to Ledger'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Proof of Payment Modal */}
      {showProofModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={closeProofModal}>
          <div className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[95vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Proof of Payment</h2>
              <button
                onClick={closeProofModal}
                className="text-white hover:text-blue-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-6 bg-gray-100">
              {proofLoading ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4"></div>
                    <p className="text-blue-700 text-lg">Loading proof file...</p>
                  </div>
                </div>
              ) : proofError ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="text-red-500 text-5xl mb-4">⚠️</div>
                    <p className="text-red-700 text-lg font-semibold">{proofError}</p>
                    <button
                      onClick={closeProofModal}
                      className="mt-4 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : proofBlobUrl && selectedDeposit ? (
                <div className="w-full h-full">
                  {isImage(selectedDeposit.upload_path) ? (
                    <div className="flex items-center justify-center min-h-[500px]">
                      <img
                        src={proofBlobUrl}
                        alt="Proof of Payment"
                        className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-lg"
                      />
                    </div>
                  ) : (
                    <div className="w-full h-[80vh]">
                      <iframe
                        src={proofBlobUrl}
                        className="w-full h-full border-0 rounded-lg shadow-lg"
                        title="Proof of Payment"
                      />
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {proofBlobUrl && (
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <p className="text-sm text-gray-600">
                  {selectedDeposit?.upload_path.split('/').pop() || 'Proof file'}
                </p>
                <div className="flex gap-3">
                  <a
                    href={proofBlobUrl}
                    download={selectedDeposit?.upload_path.split('/').pop() || 'proof.pdf'}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                  >
                    Download
                  </a>
                  <button
                    onClick={closeProofModal}
                    className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-semibold transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reject Deposit Proof Modal */}
      {showRejectModal && selectedDeposit && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={() => setShowRejectModal(false)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-red-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Reject Deposit Proof</h2>
              <button
                onClick={() => setShowRejectModal(false)}
                className="text-white hover:text-red-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>
            
            <div className="p-6 md:p-8 space-y-6">
              <div className="bg-yellow-50 border-2 border-yellow-300 rounded-xl p-4">
                <p className="text-sm text-yellow-800 font-semibold mb-2">Member: {selectedDeposit.member_name}</p>
                <p className="text-sm text-yellow-700">Amount: K{selectedDeposit.amount.toLocaleString()}</p>
                {selectedDeposit.effective_month && (
                  <p className="text-sm text-yellow-700">
                    Declaration Month: {new Date(selectedDeposit.effective_month).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="reject-comment" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  {selectedDeposit.status === 'rejected' ? 'Update Rejection Comment *' : 'Reason for Rejection *'}
                </label>
                <textarea
                  id="reject-comment"
                  value={rejectComment}
                  onChange={(e) => setRejectComment(e.target.value)}
                  required
                  rows={6}
                  className="w-full p-3 border-2 border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder={selectedDeposit.status === 'rejected' 
                    ? "Update the rejection comment if needed. The member can still respond and you can approve after reviewing their response."
                    : "Please explain what needs to be corrected. The member will see this comment and can update their declaration accordingly."}
                />
                <p className="mt-2 text-sm text-blue-700">
                  {selectedDeposit.status === 'rejected' 
                    ? "You can update this comment or approve the deposit proof if the member's response is satisfactory."
                    : "This comment will be visible to the member. They can respond and update their declaration."}
                </p>
                {selectedDeposit.member_response && (
                  <div className="mt-4 p-4 bg-blue-50 border-2 border-blue-300 rounded-xl">
                    <h4 className="font-bold text-blue-900 mb-2">Member's Response:</h4>
                    <p className="text-blue-800 whitespace-pre-wrap">{selectedDeposit.member_response}</p>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t-2 border-blue-200">
                <button
                  onClick={() => setShowRejectModal(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleRejectDeposit(selectedDeposit.id)}
                  disabled={rejecting === selectedDeposit.id || !rejectComment.trim()}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                >
                  {rejecting === selectedDeposit.id 
                    ? (selectedDeposit.status === 'rejected' ? 'Updating...' : 'Rejecting...') 
                    : (selectedDeposit.status === 'rejected' ? 'Update Rejection' : 'Reject Deposit Proof')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Loan Details Modal */}
      {showLoanModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={closeLoanModal}>
          <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[95vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Loan Performance Details</h2>
              <button
                onClick={closeLoanModal}
                className="text-white hover:text-blue-200 text-2xl font-bold"
              >
                ×
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {loadingLoanDetails ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                  <p className="mt-4 text-blue-700 text-lg">Loading loan details...</p>
                </div>
              ) : selectedLoan ? (
                <div className="space-y-6">
                  {/* Member Info */}
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <h3 className="font-bold text-lg text-blue-900 mb-2">Member Information</h3>
                    <p className="text-blue-800">
                      <span className="font-semibold">Name:</span> {selectedLoan.member_name}
                    </p>
                    {selectedLoan.member_email && (
                      <p className="text-blue-800">
                        <span className="font-semibold">Email:</span> {selectedLoan.member_email}
                      </p>
                    )}
                  </div>

                  {/* Loan Summary */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                      <p className="text-sm text-blue-700 font-medium mb-1">Loan Amount</p>
                      <p className="text-xl font-bold text-blue-900">K{selectedLoan.loan_amount.toLocaleString()}</p>
                    </div>
                    <div className="bg-red-50 border-2 border-red-200 rounded-xl p-4">
                      <p className="text-sm text-red-700 font-medium mb-1">Outstanding</p>
                      <p className="text-xl font-bold text-red-900">K{selectedLoan.outstanding_balance.toLocaleString()}</p>
                    </div>
                    <div className="bg-green-50 border-2 border-green-200 rounded-xl p-4">
                      <p className="text-sm text-green-700 font-medium mb-1">Total Paid</p>
                      <p className="text-xl font-bold text-green-900">K{selectedLoan.total_paid.toLocaleString()}</p>
                    </div>
                    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
                      <p className="text-sm text-yellow-700 font-medium mb-1">Interest Rate</p>
                      <p className="text-xl font-bold text-yellow-900">{selectedLoan.interest_rate || 'N/A'}%</p>
                    </div>
                  </div>

                  {/* Payment Breakdown */}
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <h3 className="font-bold text-lg text-blue-900 mb-3">Payment Breakdown</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div>
                        <p className="text-sm text-blue-700 font-medium mb-1">Principal Paid</p>
                        <p className="text-lg font-bold text-blue-900">K{selectedLoan.total_principal_paid.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-sm text-blue-700 font-medium mb-1">Interest Paid</p>
                        <p className="text-lg font-bold text-blue-900">K{selectedLoan.total_interest_paid.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-sm text-blue-700 font-medium mb-1">Remaining Balance</p>
                        <p className="text-lg font-bold text-red-900">K{selectedLoan.outstanding_balance.toLocaleString()}</p>
                      </div>
                    </div>
                  </div>

                  {/* Payment Performance */}
                  <div className={`border-2 rounded-xl p-4 ${
                    selectedLoan.all_payments_on_time 
                      ? 'bg-green-50 border-green-200' 
                      : 'bg-yellow-50 border-yellow-200'
                  }`}>
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">
                        {selectedLoan.all_payments_on_time ? '✅' : '⚠️'}
                      </span>
                      <div>
                        <h3 className="font-bold text-lg text-blue-900">Payment Performance</h3>
                        <p className={`font-semibold ${
                          selectedLoan.all_payments_on_time 
                            ? 'text-green-800' 
                            : 'text-yellow-800'
                        }`}>
                          {selectedLoan.payment_performance}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Repayment History */}
                  {selectedLoan.repayments && selectedLoan.repayments.length > 0 ? (
                    <div>
                      <h3 className="font-bold text-lg text-blue-900 mb-3">Repayment History</h3>
                      <div className="overflow-x-auto">
                        <table className="w-full border-collapse">
                          <thead>
                            <tr className="bg-blue-100 border-b-2 border-blue-300">
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Date</th>
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Principal</th>
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Interest</th>
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Total</th>
                              <th className="text-left p-3 text-sm md:text-base font-semibold text-blue-900">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedLoan.repayments.map((repayment, index) => (
                              <tr key={repayment.id} className="border-b border-blue-200">
                                <td className="p-3 text-sm md:text-base text-blue-800">
                                  {new Date(repayment.date).toLocaleDateString()}
                                </td>
                                <td className="p-3 text-sm md:text-base text-blue-800">
                                  K{repayment.principal.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base text-blue-800">
                                  K{repayment.interest.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base font-semibold text-blue-900">
                                  K{repayment.total.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm md:text-base">
                                  <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                                    repayment.is_on_time
                                      ? 'bg-green-200 text-green-900'
                                      : 'bg-yellow-200 text-yellow-900'
                                  }`}>
                                    {repayment.is_on_time ? 'On Time' : 'Late'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
                      <p className="text-yellow-800 font-medium">No repayments recorded yet.</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-red-700 text-lg">Failed to load loan details</p>
                </div>
              )}
            </div>

            <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={closeLoanModal}
                className="btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
