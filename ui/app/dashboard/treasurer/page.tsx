'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

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
  member_name?: string;
  member_email?: string;
  date_issued: string;
  notes?: string;
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
  status: string;
  total_principal_paid: number;
  total_interest_paid: number;
  total_interest_expected: number | null;
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
  total_interest_expected: number | null;
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
    balance: number;
    is_on_time: boolean;
  }>;
}

interface BankStatementItem {
  id: string;
  cycle_id: string;
  statement_month: string;   // "YYYY-MM-DD"
  description: string | null;
  filename: string;          // basename only
  uploaded_at: string | null;
}


export default function TreasurerDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [pendingDeposits, setPendingDeposits] = useState<PendingDeposit[]>([]);
  const [pendingPenalties, setPendingPenalties] = useState<PendingPenalty[]>([]);
  const [pendingLoans, setPendingLoans] = useState<PendingLoanApplication[]>([]);
  const [activeLoans, setActiveLoans] = useState<ActiveLoan[]>([]);
  const [loanFilter, setLoanFilter] = useState<'active' | 'paid'>('active');
  const [showAllLoans, setShowAllLoans] = useState(false);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [approvingLoan, setApprovingLoan] = useState<string | null>(null);
  const [selectedLoan, setSelectedLoan] = useState<LoanDetail | null>(null);
  const [showLoanModal, setShowLoanModal] = useState(false);
  const [loadingLoanDetails, setLoadingLoanDetails] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [selectedDepositForProof, setSelectedDepositForProof] = useState<PendingDeposit | null>(null);
  const [selectedDeposit, setSelectedDeposit] = useState<PendingDeposit | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showProofModal, setShowProofModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showLoanApprovalModal, setShowLoanApprovalModal] = useState(false);
  const [loanToApprove, setLoanToApprove] = useState<PendingLoanApplication | null>(null);
  const [rejectComment, setRejectComment] = useState('');
  const [proofBlobUrl, setProofBlobUrl] = useState<string | null>(null);
  const [proofLoading, setProofLoading] = useState(false);
  const [proofError, setProofError] = useState<string | null>(null);
  const [penaltyNotification, setPenaltyNotification] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [approvingPenalty, setApprovingPenalty] = useState<string | null>(null);

  // Bank Statements state
  const [bankStatements, setBankStatements] = useState<BankStatementItem[]>([]);
  const [showBankStmtModal, setShowBankStmtModal] = useState(false);
  const [editingStmt, setEditingStmt] = useState<BankStatementItem | null>(null);
  const [bankStmtFile, setBankStmtFile] = useState<File | null>(null);
  const [bankStmtMonth, setBankStmtMonth] = useState('');
  const [bankStmtDesc, setBankStmtDesc] = useState('');
  const [uploadingStmt, setUploadingStmt] = useState(false);

  // Reports state
  interface DeclarationReportMember {
    member_id: string;
    member_name: string;
    declaration_amount: number | null;
    is_paid: boolean;
  }
  
  interface LoanReportItem {
    loan_id: string;
    member_id: string;
    member_name: string;
    loan_amount: number;
    is_approved: boolean;
    is_disbursed: boolean;
    is_paid: boolean;
  }

  interface DeclarationDetailsReport {
    member_id: string;
    member_name: string;
    effective_month: string;
    has_declaration: boolean;
    declaration: {
      id: string;
      declared_savings_amount: number | null;
      declared_social_fund: number | null;
      declared_admin_fund: number | null;
      declared_penalties: number | null;
      declared_interest_on_loan: number | null;
      declared_loan_repayment: number | null;
      total: number;
      status: string;
    } | null;
    deposit_proof: {
      id: string;
      status: string;
      amount: number;
      uploaded_at: string | null;
    } | null;
  }
  
  const [selectedReportMonth, setSelectedReportMonth] = useState<string>(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  });
  const [declarationsReport, setDeclarationsReport] = useState<DeclarationReportMember[]>([]);
  const [loansReport, setLoansReport] = useState<LoanReportItem[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [showDeclarationDetailsModal, setShowDeclarationDetailsModal] = useState(false);
  const [declarationDetails, setDeclarationDetails] = useState<DeclarationDetailsReport | null>(null);
  const [loadingDeclarationDetails, setLoadingDeclarationDetails] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (!penaltyNotification) return;
    const timer = setTimeout(() => setPenaltyNotification(null), 4000);
    return () => clearTimeout(timer);
  }, [penaltyNotification]);

  useEffect(() => {
    loadReports();
  }, [selectedReportMonth]);

  const loadLoans = async (filter: 'active' | 'paid') => {
    const res = await api.get<ActiveLoan[]>(`/api/treasurer/loans/active?loan_filter=${filter}`);
    if (res.data) setActiveLoans(res.data);
  };

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

  const loadReports = async () => {
    setLoadingReports(true);
    try {
      const [declarationsRes, loansRes, stmtsRes] = await Promise.all([
        api.get<{ month: string; members: DeclarationReportMember[] }>(`/api/treasurer/reports/declarations?month=${selectedReportMonth}`),
        api.get<{ loans: LoanReportItem[] }>(`/api/treasurer/reports/loans?month=${selectedReportMonth}`),
        api.get<{ statements: BankStatementItem[] }>('/api/treasurer/bank-statements'),
      ]);

      if (declarationsRes.data) {
        setDeclarationsReport(declarationsRes.data.members);
      }
      if (loansRes.data) {
        setLoansReport(loansRes.data.loans);
      }
      if (stmtsRes.data) {
        setBankStatements(stmtsRes.data.statements);
      }
    } catch (err: any) {
      console.error('Error loading reports:', err);
    } finally {
      setLoadingReports(false);
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

  const copyDeclarationsReport = () => {
    const monthFormatted = formatMonth(selectedReportMonth);
    let text = `${monthFormatted} Declarations\n\n`;

    declarationsReport.forEach((member, index) => {
      const amount = member.declaration_amount != null
        ? `K${member.declaration_amount.toLocaleString()}${member.is_paid ? ' ✅' : ''}`
        : '';
      text += `${String(index + 1).padStart(2, ' ')}. ${member.member_name}${amount ? ' ' + amount : ''}\n`;
    });
    
    navigator.clipboard.writeText(text).then(() => {
      setMessage({ type: 'success', text: 'Declarations report copied to clipboard!' });
      setTimeout(() => setMessage(null), 3000);
    }).catch(() => {
      setMessage({ type: 'error', text: 'Failed to copy to clipboard' });
    });
  };

  const copyLoansReport = () => {
    let text = `Loans\n`;

    loansReport.forEach((loan, index) => {
      const status = loan.is_approved ? ' ✅' : '';
      text += `${String(index + 1).padStart(2, ' ')}. ${loan.member_name} K${loan.loan_amount.toLocaleString()}${status}\n`;
    });
    
    navigator.clipboard.writeText(text).then(() => {
      setMessage({ type: 'success', text: 'Loans report copied to clipboard!' });
      setTimeout(() => setMessage(null), 3000);
    }).catch(() => {
      setMessage({ type: 'error', text: 'Failed to copy to clipboard' });
    });
  };

  const copyFullReport = () => {
    const monthFormatted = formatMonth(selectedReportMonth);
    let text = `${monthFormatted} Declarations\n\n`;

    declarationsReport.forEach((member, index) => {
      const amount = member.declaration_amount != null
        ? `K${member.declaration_amount.toLocaleString()}${member.is_paid ? ' ✅' : ''}`
        : '';
      text += `${String(index + 1).padStart(2, ' ')}. ${member.member_name}${amount ? ' ' + amount : ''}\n`;
    });
    
    text += `\nLoans\n`;
    loansReport.forEach((loan, index) => {
      const status = loan.is_approved ? ' ✅' : '';
      text += `${String(index + 1).padStart(2, ' ')}. ${loan.member_name} K${loan.loan_amount.toLocaleString()}${status}\n`;
    });
    
    navigator.clipboard.writeText(text).then(() => {
      setMessage({ type: 'success', text: 'Full report copied to clipboard!' });
      setTimeout(() => setMessage(null), 3000);
    }).catch(() => {
      setMessage({ type: 'error', text: 'Failed to copy to clipboard' });
    });
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

  const handleViewDeclarationDetails = async (memberId: string) => {
    setLoadingDeclarationDetails(true);
    setShowDeclarationDetailsModal(true);
    setDeclarationDetails(null);
    try {
      const response = await api.get<DeclarationDetailsReport>(
        `/api/treasurer/reports/declarations/details?member_id=${encodeURIComponent(memberId)}&month=${encodeURIComponent(selectedReportMonth)}`
      );
      if (response.data) {
        setDeclarationDetails(response.data);
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to load declaration details' });
        setShowDeclarationDetailsModal(false);
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error loading declaration details' });
      setShowDeclarationDetailsModal(false);
    } finally {
      setLoadingDeclarationDetails(false);
    }
  };

  const closeDeclarationDetailsModal = () => {
    setShowDeclarationDetailsModal(false);
    setDeclarationDetails(null);
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
    // Find the loan application to show details in modal
    const loan = pendingLoans.find(l => l.id === applicationId);
    if (loan) {
      setLoanToApprove(loan);
      setShowLoanApprovalModal(true);
    }
  };

  const confirmApproveLoan = async () => {
    if (!loanToApprove) return;
    
    setApprovingLoan(loanToApprove.id);
    setMessage(null);
    try {
      const response = await api.post(`/api/treasurer/loans/${loanToApprove.id}/approve`);
      if (!response.error) {
        setMessage({ type: 'success', text: 'Loan approved, disbursed, and posted to member\'s account successfully!' });
        await loadData();
        setShowLoanApprovalModal(false);
        setLoanToApprove(null);
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

  const cancelApproveLoan = () => {
    setShowLoanApprovalModal(false);
    setLoanToApprove(null);
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

  const handleViewProof = async (uploadPath: string, deposit?: PendingDeposit) => {
    if (deposit) {
      setSelectedDepositForProof(deposit);
    }
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
    setSelectedDepositForProof(null);
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

  const openUploadStmtModal = () => {
    setEditingStmt(null);
    setBankStmtFile(null);
    setBankStmtMonth('');
    setBankStmtDesc('');
    setShowBankStmtModal(true);
  };

  const openEditStmtModal = (stmt: BankStatementItem) => {
    setEditingStmt(stmt);
    setBankStmtFile(null);
    setBankStmtMonth(stmt.statement_month.substring(0, 7)); // YYYY-MM
    setBankStmtDesc(stmt.description || '');
    setShowBankStmtModal(true);
  };

  const closeBankStmtModal = () => {
    setShowBankStmtModal(false);
    setEditingStmt(null);
    setBankStmtFile(null);
  };

  const handleViewStatement = async (stmt: BankStatementItem) => {
    setProofLoading(true);
    setProofError(null);
    setShowProofModal(true);
    setSelectedDepositForProof({ upload_path: stmt.filename } as any);
    try {
      const blobUrl = await api.getFileBlob(`/api/treasurer/bank-statements/file/${encodeURIComponent(stmt.filename)}`);
      setProofBlobUrl(blobUrl);
    } catch (error) {
      setProofError(error instanceof Error ? error.message : 'Failed to load file');
      setProofBlobUrl(null);
    } finally {
      setProofLoading(false);
    }
  };

  const handleSubmitBankStmt = async () => {
    if (!editingStmt && !bankStmtFile) {
      setMessage({ type: 'error', text: 'Please select a file to upload.' });
      return;
    }
    if (!bankStmtMonth) {
      setMessage({ type: 'error', text: 'Please select a month.' });
      return;
    }

    setUploadingStmt(true);
    try {
      const formData = new FormData();
      const monthDate = `${bankStmtMonth}-01`;
      formData.append('month', monthDate);
      if (bankStmtDesc) formData.append('description', bankStmtDesc);
      if (bankStmtFile) formData.append('file', bankStmtFile);

      let response;
      if (editingStmt) {
        response = await api.putFormData(`/api/treasurer/bank-statements/${editingStmt.id}`, formData);
      } else {
        response = await api.postFormData('/api/treasurer/bank-statements', formData);
      }

      if (!response.error) {
        setMessage({ type: 'success', text: editingStmt ? 'Bank statement updated.' : 'Bank statement uploaded.' });
        closeBankStmtModal();
        await loadReports();
      } else {
        setMessage({ type: 'error', text: response.error });
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Error saving bank statement' });
    } finally {
      setUploadingStmt(false);
      setTimeout(() => setMessage(null), 5000);
    }
  };

  const handleApprovePenalty = async (penaltyId: string) => {
    setApprovingPenalty(penaltyId);
    setPenaltyNotification(null);
    try {
      const response = await api.post(`/api/treasurer/penalties/${penaltyId}/approve`);
      if (!response.error) {
        setPenaltyNotification({ type: 'success', text: 'Penalty approved and posted successfully' });
        loadData();
      } else {
        setPenaltyNotification({ type: 'error', text: 'Error: ' + response.error });
      }
    } catch (err: any) {
      setPenaltyNotification({ type: 'error', text: err?.message || 'Failed to approve penalty' });
    } finally {
      setApprovingPenalty(null);
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
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Treasurer Dashboard</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
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

        {penaltyNotification && (
          <div
            className={`mb-4 md:mb-6 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium ${
              penaltyNotification.type === 'success'
                ? 'bg-green-100 border-2 border-green-400 text-green-800'
                : 'bg-red-100 border-2 border-red-400 text-red-800'
            }`}
            role="alert"
          >
            {penaltyNotification.type === 'success' ? '✓ ' : ''}
            {penaltyNotification.text}
          </div>
        )}

        {/* Quick Actions */}
        <div className="mb-4 flex gap-3">
          <Link
            href="/dashboard/reconcile"
            className="inline-flex items-center px-4 py-2 bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-600 text-white rounded-lg font-semibold text-sm hover:from-blue-600 hover:to-blue-700 transition-all"
          >
            Reconciliation
          </Link>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
            <p className="mt-4 text-blue-700 text-lg">Loading...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
            {/* Pending Deposit Proofs - Compact Card */}
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg md:text-xl font-bold text-blue-900">Pending Deposit Proofs</h2>
                {pendingDeposits.length > 0 && (
                  <span className="px-3 py-1 bg-blue-600 text-white rounded-full text-sm font-semibold">
                    {pendingDeposits.length}
                  </span>
                )}
              </div>
              
              {pendingDeposits.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No pending deposit proofs</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {pendingDeposits.slice(0, 3).map((deposit) => (
                    <div
                      key={deposit.id}
                      className="p-3 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-lg hover:shadow-md transition-shadow"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm text-blue-900 truncate">
                            {deposit.member_name}
                          </p>
                          <p className="text-xs text-blue-700">
                            K{deposit.amount.toLocaleString()}
                          </p>
                          {deposit.effective_month && (
                            <p className="text-xs text-blue-600 truncate">
                              {(() => {
                                const [year, month] = deposit.effective_month.split('-').map(Number);
                                const date = new Date(year, month - 1, 1);
                                return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
                              })()}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-col gap-1 flex-shrink-0">
                          <button
                            onClick={() => handleViewDetails(deposit)}
                            className="px-2 py-1 bg-blue-500 text-white rounded text-xs font-semibold hover:bg-blue-600 transition-colors"
                          >
                            View
                          </button>
                          {deposit.status === 'submitted' && (
                            <button
                              onClick={() => handleApproveDeposit(deposit.id)}
                              disabled={approving === deposit.id}
                              className="px-2 py-1 bg-green-600 text-white rounded text-xs font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors"
                            >
                              {approving === deposit.id ? '...' : 'Approve'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  {pendingDeposits.length > 3 && (
                    <p className="text-xs text-blue-600 text-center pt-2">
                      +{pendingDeposits.length - 3} more
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Pending Loan Applications - Compact Card */}
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg md:text-xl font-bold text-blue-900">Pending Loan Applications</h2>
                {pendingLoans.length > 0 && (
                  <span className="px-3 py-1 bg-blue-600 text-white rounded-full text-sm font-semibold">
                    {pendingLoans.length}
                  </span>
                )}
              </div>
              
              {pendingLoans.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No pending loan applications</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {pendingLoans.slice(0, 3).map((loan) => (
                    <div
                      key={loan.id}
                      className="p-3 bg-gradient-to-r from-blue-50 to-blue-100 border-2 border-blue-300 rounded-lg hover:shadow-md transition-shadow"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm text-blue-900 truncate">
                            {loan.member_name}
                          </p>
                          <p className="text-xs text-blue-700">
                            K{loan.amount.toLocaleString()} • {loan.term_months} {loan.term_months === '1' ? 'Month' : 'Months'}
                          </p>
                        </div>
                        <button
                          onClick={() => handleApproveLoan(loan.id)}
                          disabled={approvingLoan === loan.id}
                          className="px-2 py-1 bg-green-600 text-white rounded text-xs font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors flex-shrink-0"
                        >
                          {approvingLoan === loan.id ? '...' : 'Approve'}
                        </button>
                      </div>
                    </div>
                  ))}
                  {pendingLoans.length > 3 && (
                    <p className="text-xs text-blue-600 text-center pt-2">
                      +{pendingLoans.length - 3} more
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Loans - Compact Card */}
            <div className="card">
              <div className="flex justify-between items-center mb-3">
                <h2 className="text-lg md:text-xl font-bold text-blue-900">Loans</h2>
                <span className="px-3 py-1 bg-green-600 text-white rounded-full text-sm font-semibold">
                  {activeLoans.length}
                </span>
              </div>

              {/* Filter tabs */}
              <div className="flex gap-2 mb-3">
                <button
                  onClick={() => { if (loanFilter !== 'active') { setLoanFilter('active'); setShowAllLoans(false); loadLoans('active'); } }}
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                    loanFilter === 'active'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-blue-700 border-blue-300 hover:bg-blue-50'
                  }`}
                >
                  Active
                </button>
                <button
                  onClick={() => { if (loanFilter !== 'paid') { setLoanFilter('paid'); setShowAllLoans(false); loadLoans('paid'); } }}
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                    loanFilter === 'paid'
                      ? 'bg-green-600 text-white border-green-600'
                      : 'bg-white text-green-700 border-green-300 hover:bg-green-50'
                  }`}
                >
                  Paid Off
                </button>
              </div>

              {activeLoans.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">
                  {loanFilter === 'paid' ? 'No paid-off loans' : 'No active loans'}
                </p>
              ) : (
                <div className="space-y-2 max-h-[460px] overflow-y-auto">
                  {(showAllLoans ? activeLoans : activeLoans.slice(0, 3)).map((loan) => (
                    <div
                      key={loan.id}
                      className="p-3 bg-gradient-to-r from-green-50 to-green-100 border-2 border-green-300 rounded-lg hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => handleViewLoanDetails(loan.id)}
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm text-blue-900 truncate mb-1.5">
                            {loan.member_name}
                          </p>
                          <div className="space-y-0.5">
                            <div className="flex justify-between text-xs">
                              <span className="text-blue-500">Principal Amount</span>
                              <span className="font-semibold text-blue-900">K{loan.loan_amount.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-green-600">Principal Paid</span>
                              <span className="font-semibold text-green-800">K{loan.total_principal_paid.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-orange-500">Interest on Loan</span>
                              <span className="font-semibold text-orange-700">
                                {loan.total_interest_expected != null ? `K${loan.total_interest_expected.toLocaleString()}` : 'N/A'}
                              </span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-orange-400">Interest Paid</span>
                              <span className="font-semibold text-orange-600">K{loan.total_interest_paid.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between text-xs border-t border-green-200 pt-0.5 mt-0.5">
                              <span className="text-red-500 font-medium">Outstanding</span>
                              <span className="font-bold text-red-700">K{loan.outstanding_balance.toLocaleString()}</span>
                            </div>
                          </div>
                        </div>
                        <span className="text-xs text-blue-600 flex-shrink-0 mt-1">→</span>
                      </div>
                    </div>
                  ))}
                  {activeLoans.length > 3 && (
                    <button
                      onClick={() => setShowAllLoans(prev => !prev)}
                      className="w-full text-xs text-blue-600 font-semibold text-center pt-2 hover:text-blue-800 transition-colors"
                    >
                      {showAllLoans
                        ? 'Show less'
                        : `+${activeLoans.length - 3} more`}
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Pending Penalties - Compact Card */}
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg md:text-xl font-bold text-blue-900">Pending Penalties</h2>
                {pendingPenalties.length > 0 && (
                  <span className="px-3 py-1 bg-yellow-600 text-white rounded-full text-sm font-semibold">
                    {pendingPenalties.length}
                  </span>
                )}
              </div>
              
              {pendingPenalties.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No pending penalties</p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {pendingPenalties.slice(0, 3).map((penalty) => (
                    <div
                      key={penalty.id}
                      className="p-3 bg-gradient-to-r from-yellow-50 to-yellow-100 border-2 border-yellow-300 rounded-lg hover:shadow-md transition-shadow"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-sm text-blue-900 truncate">
                            {penalty.penalty_type?.name || 'Penalty'}
                          </p>
                          <p className="text-xs text-blue-700 truncate">
                            {penalty.member_name || 'Unknown'}
                          </p>
                          <p className="text-xs text-blue-700">
                            K{parseFloat(penalty.penalty_type?.fee_amount || '0').toLocaleString()}
                          </p>
                        </div>
                        <button
                          onClick={() => handleApprovePenalty(penalty.id)}
                          disabled={approvingPenalty === penalty.id}
                          className="px-2 py-1 bg-green-600 text-white rounded text-xs font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors flex-shrink-0"
                        >
                          {approvingPenalty === penalty.id ? '...' : 'Approve'}
                        </button>
                      </div>
                    </div>
                  ))}
                  {pendingPenalties.length > 3 && (
                    <p className="text-xs text-blue-600 text-center pt-2">
                      +{pendingPenalties.length - 3} more
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Reports Card */}
            <div className="card md:col-span-2">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg md:text-xl font-bold text-blue-900">Reports</h2>
                <button
                  onClick={copyFullReport}
                  className="px-3 py-1 bg-blue-600 text-white rounded text-sm font-semibold hover:bg-blue-700 transition-colors"
                >
                  Copy Full Report
                </button>
              </div>

              <div className="space-y-6">
                {/* Month Selector */}
                <div className="flex items-center gap-4">
                  <label className="text-sm font-semibold text-blue-900">Select Month:</label>
                  <input
                    type="month"
                    value={selectedReportMonth.substring(0, 7)}
                    onChange={(e) => {
                      const [year, month] = e.target.value.split('-').map(Number);
                      setSelectedReportMonth(`${year}-${String(month).padStart(2, '0')}-01`);
                    }}
                    className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                {loadingReports ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-200 border-t-blue-600 mx-auto"></div>
                    <p className="mt-2 text-blue-700 text-sm">Loading reports...</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Declarations Report */}
                    <div className="bg-white border-2 border-blue-200 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="text-base font-bold text-blue-900">
                          {formatMonth(selectedReportMonth)} Declarations
                        </h3>
                        <button
                          onClick={copyDeclarationsReport}
                          className="px-2 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition-colors"
                        >
                          Copy
                        </button>
                      </div>
                      <div className="max-h-[500px] overflow-y-auto space-y-1 text-sm font-mono">
                        {declarationsReport.length === 0 ? (
                          <p className="text-blue-700 text-center py-4">No members for this month</p>
                        ) : (
                          declarationsReport.map((member, index) => (
                            <div key={member.member_id} className="flex items-center gap-2 py-1">
                              <span className="text-blue-600 w-6 text-right">
                                {String(index + 1).padStart(2, ' ')}.
                              </span>
                              <button
                                type="button"
                                onClick={() => handleViewDeclarationDetails(member.member_id)}
                                className="flex-1 text-left text-blue-900 hover:text-blue-600 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-400 rounded px-1 -mx-1"
                              >
                                {member.member_name}
                              </button>
                              <span className="flex items-center gap-1 text-blue-700 font-semibold">
                                {member.declaration_amount != null
                                  ? `K${member.declaration_amount.toLocaleString()}`
                                  : ''}
                                {member.declaration_amount != null && member.is_paid && (
                                  <span className="inline-flex items-center justify-center w-5 h-5 bg-green-500 rounded text-white text-xs font-bold">✓</span>
                                )}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Loans Report */}
                    <div className="bg-white border-2 border-green-200 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="text-base font-bold text-green-900">Loans</h3>
                        <button
                          onClick={copyLoansReport}
                          className="px-2 py-1 bg-green-600 text-white rounded text-xs font-semibold hover:bg-green-700 transition-colors"
                        >
                          Copy
                        </button>
                      </div>
                      <div className="max-h-[500px] overflow-y-auto space-y-1 text-sm font-mono">
                        {loansReport.length === 0 ? (
                          <p className="text-green-700 text-center py-4">No loan applications</p>
                        ) : (
                          loansReport.map((loan, index) => (
                            <div key={loan.loan_id} className="flex items-center gap-2 py-1">
                              <span className="text-green-600 w-6 text-right">
                                {String(index + 1).padStart(2, ' ')}.
                              </span>
                              {loan.is_approved ? (
                                <button
                                  type="button"
                                  onClick={() => handleViewLoanDetails(loan.loan_id)}
                                  className="flex-1 text-left text-green-900 hover:text-green-600 hover:underline focus:outline-none focus:ring-2 focus:ring-green-400 rounded px-1 -mx-1"
                                >
                                  {loan.member_name}
                                </button>
                              ) : (
                                <span className="flex-1 text-green-900">
                                  {loan.member_name}
                                </span>
                              )}
                              <span className="flex items-center gap-1 text-green-700 font-semibold">
                                K{loan.loan_amount.toLocaleString()}
                                {loan.is_approved && (
                                  <span className="inline-flex items-center justify-center w-5 h-5 bg-green-500 rounded text-white text-xs font-bold">✓</span>
                                )}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Bank Statements Panel */}
                <div className="bg-white border-2 border-purple-200 rounded-lg p-4">
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="text-base font-bold text-purple-900">Bank Statements</h3>
                    <button
                      onClick={openUploadStmtModal}
                      className="px-3 py-1 bg-purple-600 text-white rounded text-xs font-semibold hover:bg-purple-700 transition-colors"
                    >
                      + Upload
                    </button>
                  </div>
                  {bankStatements.length === 0 ? (
                    <p className="text-purple-700 text-sm text-center py-4">No bank statements for this cycle</p>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {bankStatements.map((stmt, index) => (
                        <div key={stmt.id} className="flex items-center gap-2 py-1 text-sm font-mono">
                          <span className="text-purple-600 w-6 text-right">{String(index + 1).padStart(2, ' ')}.</span>
                          <span className="flex-1 text-purple-900 font-semibold">{formatMonth(stmt.statement_month)}</span>
                          {stmt.description && (
                            <span className="text-purple-700 text-xs truncate max-w-[180px]">{stmt.description}</span>
                          )}
                          <button
                            onClick={() => handleViewStatement(stmt)}
                            className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs font-semibold hover:bg-purple-200 transition-colors flex-shrink-0"
                          >
                            View
                          </button>
                          <button
                            onClick={() => openEditStmtModal(stmt)}
                            className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-semibold hover:bg-gray-200 transition-colors flex-shrink-0"
                          >
                            Edit
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

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
                      {formatMonth(selectedDeposit.effective_month)}
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
                  onClick={() => handleViewProof(selectedDeposit.upload_path, selectedDeposit)}
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
              ) : proofBlobUrl && selectedDepositForProof ? (
                <div className="w-full h-full">
                  {isImage(selectedDepositForProof.upload_path) ? (
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

            {proofBlobUrl && selectedDepositForProof && (
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <p className="text-sm text-gray-600">
                  {selectedDepositForProof.upload_path.split('/').pop() || 'Proof file'}
                </p>
                <div className="flex gap-3">
                  <a
                    href={proofBlobUrl}
                    download={selectedDepositForProof.upload_path.split('/').pop() || 'proof.pdf'}
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
                    Declaration Month: {formatMonth(selectedDeposit.effective_month)}
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

                  {/* Loan Summary — 5-row breakdown */}
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4 space-y-3">
                    <div className="flex justify-between items-center py-1 border-b border-blue-200">
                      <p className="text-sm font-medium text-blue-700">Principal Amount</p>
                      <p className="text-base font-bold text-blue-900">K{selectedLoan.loan_amount.toLocaleString()}</p>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-blue-200">
                      <p className="text-sm font-medium text-green-700">Principal Paid</p>
                      <p className="text-base font-bold text-green-900">K{selectedLoan.total_principal_paid.toLocaleString()}</p>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-blue-200">
                      <p className="text-sm font-medium text-orange-600">
                        Interest on Loan
                        {selectedLoan.interest_rate ? ` (${selectedLoan.interest_rate}% × ${selectedLoan.term_months} months)` : ''}
                      </p>
                      <p className="text-base font-bold text-orange-700">
                        {selectedLoan.total_interest_expected != null
                          ? `K${selectedLoan.total_interest_expected.toLocaleString()}`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-blue-200">
                      <p className="text-sm font-medium text-orange-500">Interest Paid</p>
                      <p className="text-base font-bold text-orange-600">K{selectedLoan.total_interest_paid.toLocaleString()}</p>
                    </div>
                    <div className="flex justify-between items-center py-1">
                      <p className="text-sm font-semibold text-red-700">Outstanding</p>
                      <p className="text-lg font-bold text-red-900">K{selectedLoan.outstanding_balance.toLocaleString()}</p>
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
                              <th className="text-left p-3 text-sm font-semibold text-blue-900">Date</th>
                              <th className="text-right p-3 text-sm font-semibold text-blue-900">Principal</th>
                              <th className="text-right p-3 text-sm font-semibold text-blue-900">Interest</th>
                              <th className="text-right p-3 text-sm font-semibold text-blue-900">Total Paid</th>
                              <th className="text-right p-3 text-sm font-semibold text-blue-900">Balance</th>
                            </tr>
                          </thead>
                          <tbody>
                            {/* Opening balance row */}
                            <tr className="border-b border-blue-200 bg-blue-50">
                              <td className="p-3 text-sm text-blue-500 italic" colSpan={4}>Opening balance</td>
                              <td className="p-3 text-right text-sm font-semibold text-blue-900">
                                K{selectedLoan.loan_amount.toLocaleString()}
                              </td>
                            </tr>
                            {selectedLoan.repayments.map((repayment) => (
                              <tr key={repayment.id} className="border-b border-blue-200 hover:bg-blue-50">
                                <td className="p-3 text-sm text-blue-800">
                                  {new Date(repayment.date + 'T00:00:00').toLocaleDateString()}
                                </td>
                                <td className="p-3 text-sm text-right text-green-700 font-medium">
                                  K{repayment.principal.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm text-right text-orange-600">
                                  K{repayment.interest.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm text-right font-semibold text-blue-900">
                                  K{repayment.total.toLocaleString()}
                                </td>
                                <td className="p-3 text-sm text-right font-bold text-red-700">
                                  K{(repayment.balance ?? 0).toLocaleString()}
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

      {/* Declaration Details Modal (Reports - view only) */}
      {showDeclarationDetailsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" onClick={closeDeclarationDetailsModal}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Declaration Details</h2>
              <button
                onClick={closeDeclarationDetailsModal}
                className="text-white hover:text-blue-200 text-2xl font-bold"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {loadingDeclarationDetails ? (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto" />
                  <p className="mt-4 text-blue-700 text-lg">Loading declaration details...</p>
                </div>
              ) : declarationDetails ? (
                <div className="space-y-6">
                  <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
                    <h3 className="font-bold text-lg text-blue-900 mb-2">Member</h3>
                    <p className="text-blue-800 font-semibold">{declarationDetails.member_name}</p>
                    <p className="text-blue-700 text-sm mt-1">
                      Effective month: {formatMonth(declarationDetails.effective_month)}
                    </p>
                  </div>
                  {!declarationDetails.has_declaration ? (
                    <div className="bg-yellow-50 border-2 border-yellow-200 rounded-xl p-4">
                      <p className="text-yellow-800 font-medium">No declaration for this month.</p>
                    </div>
                  ) : declarationDetails.declaration ? (
                    <>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {declarationDetails.declaration.declared_savings_amount != null && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Savings</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_savings_amount.toLocaleString()}</p>
                          </div>
                        )}
                        {declarationDetails.declaration.declared_social_fund != null && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Social Fund</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_social_fund.toLocaleString()}</p>
                          </div>
                        )}
                        {declarationDetails.declaration.declared_admin_fund != null && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Admin Fund</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_admin_fund.toLocaleString()}</p>
                          </div>
                        )}
                        {declarationDetails.declaration.declared_penalties != null && declarationDetails.declaration.declared_penalties > 0 && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Penalties</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_penalties.toLocaleString()}</p>
                          </div>
                        )}
                        {declarationDetails.declaration.declared_interest_on_loan != null && declarationDetails.declaration.declared_interest_on_loan > 0 && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Interest on Loan</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_interest_on_loan.toLocaleString()}</p>
                          </div>
                        )}
                        {declarationDetails.declaration.declared_loan_repayment != null && declarationDetails.declaration.declared_loan_repayment > 0 && (
                          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                            <p className="text-xs text-gray-600 font-medium">Loan Repayment</p>
                            <p className="font-semibold text-gray-900">K{declarationDetails.declaration.declared_loan_repayment.toLocaleString()}</p>
                          </div>
                        )}
                      </div>
                      <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4 flex justify-between items-center">
                        <span className="font-bold text-blue-900">Total</span>
                        <span className="text-xl font-bold text-blue-900">K{declarationDetails.declaration.total.toLocaleString()}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-700">Declaration status:</span>
                        <span className={`px-2 py-1 rounded text-sm font-semibold ${
                          declarationDetails.declaration.status === 'approved' ? 'bg-green-200 text-green-900' :
                          declarationDetails.declaration.status === 'pending' ? 'bg-yellow-200 text-yellow-900' :
                          declarationDetails.declaration.status === 'proof' ? 'bg-blue-200 text-blue-900' :
                          declarationDetails.declaration.status === 'rejected' ? 'bg-red-200 text-red-900' :
                          'bg-gray-200 text-gray-800'
                        }`}>
                          {declarationDetails.declaration.status === 'proof' ? 'Proof Submitted' : declarationDetails.declaration.status}
                        </span>
                      </div>
                      {declarationDetails.deposit_proof && (
                        <div className="bg-gray-50 border-2 border-gray-200 rounded-xl p-4">
                          <h3 className="font-bold text-lg text-gray-900 mb-2">Deposit Proof</h3>
                          <div className="space-y-1 text-sm">
                            <p><span className="font-medium text-gray-700">Status:</span> {declarationDetails.deposit_proof.status}</p>
                            <p><span className="font-medium text-gray-700">Amount:</span> K{declarationDetails.deposit_proof.amount.toLocaleString()}</p>
                            {declarationDetails.deposit_proof.uploaded_at && (
                              <p><span className="font-medium text-gray-700">Uploaded:</span> {new Date(declarationDetails.deposit_proof.uploaded_at).toLocaleString()}</p>
                            )}
                          </div>
                        </div>
                      )}
                    </>
                  ) : null}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-red-700 text-lg">Failed to load declaration details.</p>
                </div>
              )}
            </div>
            <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={closeDeclarationDetailsModal}
                className="btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loan Approval Confirmation Modal */}
      {showLoanApprovalModal && loanToApprove && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={cancelApproveLoan}>
          <div
            className="bg-white rounded-xl shadow-2xl max-w-md w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl">
              <h2 className="text-xl md:text-2xl font-bold">Confirm Loan Approval</h2>
            </div>

            <div className="p-6 md:p-8">
              <div className="mb-6">
                <p className="text-base md:text-lg text-blue-900 mb-4">
                  Are you sure you want to approve and disburse this loan?
                </p>
                <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-blue-700 font-medium">Member:</span>
                    <span className="text-sm text-blue-900 font-semibold">{loanToApprove.member_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-blue-700 font-medium">Loan Amount:</span>
                    <span className="text-sm text-blue-900 font-semibold">K{loanToApprove.amount.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-blue-700 font-medium">Term:</span>
                    <span className="text-sm text-blue-900 font-semibold">
                      {loanToApprove.term_months} {loanToApprove.term_months === '1' ? 'Month' : 'Months'}
                    </span>
                  </div>
                </div>
                <div className="mt-4 p-3 bg-yellow-50 border-2 border-yellow-300 rounded-xl">
                  <p className="text-sm text-yellow-800 font-medium">
                    ⚠️ This will post the loan to the member's account and make it active.
                  </p>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row justify-end gap-3 pt-4 border-t-2 border-gray-200">
                <button
                  type="button"
                  onClick={cancelApproveLoan}
                  disabled={approvingLoan === loanToApprove.id}
                  className="btn-secondary disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmApproveLoan}
                  disabled={approvingLoan === loanToApprove.id}
                  className="px-4 py-2 md:px-6 md:py-3 bg-gradient-to-br from-green-500 to-green-600 border-2 border-green-600 text-white rounded-xl hover:from-green-600 hover:to-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold transition-all duration-200"
                >
                  {approvingLoan === loanToApprove.id ? 'Approving...' : 'Approve & Disburse Loan'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bank Statement Upload/Edit Modal */}
      {showBankStmtModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={closeBankStmtModal}>
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full" onClick={(e) => e.stopPropagation()}>
            <div className="bg-purple-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl font-bold">{editingStmt ? 'Edit Bank Statement' : 'Upload Bank Statement'}</h2>
              <button onClick={closeBankStmtModal} className="text-white hover:text-purple-200 text-2xl font-bold">×</button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-semibold text-blue-900 mb-1">Statement Month *</label>
                <input
                  type="month"
                  value={bankStmtMonth}
                  onChange={(e) => setBankStmtMonth(e.target.value)}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-blue-900 mb-1">Description / Narration</label>
                <textarea
                  value={bankStmtDesc}
                  onChange={(e) => setBankStmtDesc(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. Monthly reconciliation"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-blue-900 mb-1">
                  {editingStmt ? 'Replace File (optional)' : 'File *'} <span className="text-xs font-normal text-blue-600">PDF, JPG, PNG</span>
                </label>
                {editingStmt && (
                  <p className="text-xs text-blue-600 mb-1">Current: {editingStmt.filename}</p>
                )}
                <input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={(e) => setBankStmtFile(e.target.files?.[0] || null)}
                  className="w-full text-sm text-blue-900 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-purple-100 file:text-purple-700 hover:file:bg-purple-200"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button onClick={closeBankStmtModal} className="btn-secondary">Cancel</button>
                <button
                  onClick={handleSubmitBankStmt}
                  disabled={uploadingStmt}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm font-semibold transition-colors"
                >
                  {uploadingStmt ? 'Saving...' : (editingStmt ? 'Save Changes' : 'Upload')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
