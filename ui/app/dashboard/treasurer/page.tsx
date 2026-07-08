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
  maturity_date?: string;
  status: string;
  performance_status?: 'on_track' | 'at_risk' | 'defaulting' | 'paid';
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
  const [loanFilter, setLoanFilter] = useState<'active' | 'at_risk' | 'defaulting' | 'paid'>('active');
  const [loanNameQuery, setLoanNameQuery] = useState('');
  const [showAllLoans, setShowAllLoans] = useState(false);
  const [showAllDeposits, setShowAllDeposits] = useState(false);
  const [showAllPendingLoans, setShowAllPendingLoans] = useState(false);
  const [showAllPenalties, setShowAllPenalties] = useState(false);
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
  const [loanApprovalForce, setLoanApprovalForce] = useState(false);
  // Treasurer overrides that can be applied at approval time
  const [approveAmount, setApproveAmount] = useState<string>('');
  const [approveTerm, setApproveTerm] = useState<string>('');
  const [approveNote, setApproveNote] = useState<string>('');
  // Optional surcharge penalty (e.g. Emergency Loan K150) to issue at disbursement
  const [approveSurchargePenaltyId, setApproveSurchargePenaltyId] = useState<string>('');
  const [approvalPenaltyTypes, setApprovalPenaltyTypes] = useState<
    { id: string; name: string; description: string | null; fee_amount: string }[]
  >([]);

  // Backfill-loan modal (Reports → Loans section)
  const [showBackfillModal, setShowBackfillModal] = useState(false);
  const [backfillMemberId, setBackfillMemberId] = useState('');
  const [backfillAmount, setBackfillAmount] = useState('');
  const [backfillTerm, setBackfillTerm] = useState('1');
  const [backfillRate, setBackfillRate] = useState('');
  const [backfillSuggestedRate, setBackfillSuggestedRate] = useState<number | null>(null);
  const [backfillDate, setBackfillDate] = useState(''); // YYYY-MM-DD
  const [backfillReason, setBackfillReason] = useState('');
  const [backfillForce, setBackfillForce] = useState(false);
  const [backfillCycleId, setBackfillCycleId] = useState('');
  const [backfillMembers, setBackfillMembers] = useState<{ id: string; user: { first_name: string; last_name: string } }[]>([]);
  const [backfillCycles, setBackfillCycles] = useState<{ id: string; year: number; cycle_number: number }[]>([]);
  const [backfillSubmitting, setBackfillSubmitting] = useState(false);
  // Inline modal-level error + which field to highlight red. Keeps the
  // feedback next to what the treasurer is looking at instead of the
  // page-level toast that they can't see behind the modal.
  const [backfillError, setBackfillError] = useState<string | null>(null);
  const [backfillErrorField, setBackfillErrorField] = useState<
    'member' | 'cycle' | 'amount' | 'term' | 'rate' | 'date' | 'reason' | null
  >(null);

  // Move-disbursement-month modal (per-loan action in Reports → Loans)
  const [moveLoan, setMoveLoan] = useState<LoanReportItem | null>(null);
  const [moveLoanNewDate, setMoveLoanNewDate] = useState('');
  const [moveLoanReason, setMoveLoanReason] = useState('');
  const [moveLoanSubmitting, setMoveLoanSubmitting] = useState(false);
  const [moveLoanError, setMoveLoanError] = useState<string | null>(null);
  const [moveLoanErrorField, setMoveLoanErrorField] = useState<'date' | 'reason' | null>(null);
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

  // Inline-edit state for the bank statements list (no modal): which row is
  // being edited + buffered values for that row. Saves call the same PUT
  // endpoint the modal already uses.
  const [inlineEditStmtId, setInlineEditStmtId] = useState<string | null>(null);
  const [inlineStmtMonth, setInlineStmtMonth] = useState('');
  const [inlineStmtDesc, setInlineStmtDesc] = useState('');
  const [inlineStmtFile, setInlineStmtFile] = useState<File | null>(null);
  const [inlineStmtSaving, setInlineStmtSaving] = useState(false);

  const startInlineEditStmt = (stmt: BankStatementItem) => {
    setInlineEditStmtId(stmt.id);
    setInlineStmtMonth(stmt.statement_month.substring(0, 7)); // YYYY-MM
    setInlineStmtDesc(stmt.description || '');
    setInlineStmtFile(null);
  };

  const cancelInlineEditStmt = () => {
    setInlineEditStmtId(null);
    setInlineStmtFile(null);
  };

  const saveInlineEditStmt = async (stmtId: string) => {
    if (!inlineStmtMonth) {
      setMessage({ type: 'error', text: 'Please select a month.' });
      return;
    }
    setInlineStmtSaving(true);
    try {
      const formData = new FormData();
      formData.append('month', `${inlineStmtMonth}-01`);
      formData.append('description', inlineStmtDesc || '');
      if (inlineStmtFile) formData.append('file', inlineStmtFile);
      const response = await api.putFormData(`/api/treasurer/bank-statements/${stmtId}`, formData);
      if (response.error) {
        setMessage({ type: 'error', text: response.error });
      } else {
        setMessage({ type: 'success', text: 'Bank statement updated.' });
        cancelInlineEditStmt();
        await loadReports();
      }
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Error saving bank statement' });
    } finally {
      setInlineStmtSaving(false);
      setTimeout(() => setMessage(null), 5000);
    }
  };
  const [uploadingStmt, setUploadingStmt] = useState(false);

  // Penalty Reversals state
  interface PendingReversal {
    id: string;
    member_name: string;
    penalty_type_name: string;
    fee_amount: number;
    date_issued: string | null;
    notes: string | null;
    reversal_reason: string;
    reversal_requested_by_name: string | null;
    reversal_requested_at: string | null;
  }
  const [pendingReversals, setPendingReversals] = useState<PendingReversal[]>([]);
  const [approvingReversalId, setApprovingReversalId] = useState<string | null>(null);

  // Payment Requests state
  interface ApprovedPaymentRequest {
    id: string;
    amount: number;
    description: string;
    category: string;
    source_account_code: string;
    beneficiary_name: string;
    initiator_name?: string;
    approver_name?: string;
    approved_at?: string;
    status: string;
  }
  const [approvedPayments, setApprovedPayments] = useState<ApprovedPaymentRequest[]>([]);
  const [executingPaymentId, setExecutingPaymentId] = useState<string | null>(null);
  const [paymentReference, setPaymentReference] = useState('');
  const [executingPayment, setExecutingPayment] = useState(false);

  // Reports state
  interface DeclarationReportMember {
    member_id: string;
    member_name: string;
    declaration_id: string | null;
    declaration_amount: number | null;
    is_paid: boolean;
    is_phantom?: boolean;
    has_real_proof?: boolean;
    created_via_reconciliation?: boolean;
    approved_via_reconciliation?: boolean;
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
      upload_path?: string | null;
      has_file?: boolean;
    } | null;
  }
  
  const [selectedReportMonth, setSelectedReportMonth] = useState<string>(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  });
  const [declarationsReport, setDeclarationsReport] = useState<DeclarationReportMember[]>([]);
  const [loansReport, setLoansReport] = useState<LoanReportItem[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [totalDeclared, setTotalDeclared] = useState(0);
  const [totalDeposited, setTotalDeposited] = useState(0);
  const [totalLoansApplied, setTotalLoansApplied] = useState(0);
  const [totalLoansDisbursed, setTotalLoansDisbursed] = useState(0);
  const [showDeclarationDetailsModal, setShowDeclarationDetailsModal] = useState(false);
  const [declarationDetails, setDeclarationDetails] = useState<DeclarationDetailsReport | null>(null);
  const [loadingDeclarationDetails, setLoadingDeclarationDetails] = useState(false);

  // Reject-declaration modal state
  const [rejectTarget, setRejectTarget] = useState<DeclarationReportMember | null>(null);
  const [rejectDeclComment, setRejectDeclComment] = useState('');
  const [rejectingDecl, setRejectingDecl] = useState(false);

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

  const loadLoans = async (filter: 'active' | 'at_risk' | 'defaulting' | 'paid') => {
    const res = await api.get<ActiveLoan[]>(`/api/treasurer/loans/active?loan_filter=${filter}`);
    if (res.data) {
      setActiveLoans(res.data);
    } else if (res.error) {
      console.error('Loans fetch error:', res.error);
    }
  };

  const loadData = async () => {
    const [depositsRes, penaltiesRes, loansRes, activeLoansRes, paymentsRes, reversalsRes] = await Promise.all([
      api.get<PendingDeposit[]>('/api/treasurer/deposits/pending'),
      api.get<PendingPenalty[]>('/api/treasurer/penalties/pending'),
      api.get<PendingLoanApplication[]>('/api/treasurer/loans/pending'),
      api.get<ActiveLoan[]>('/api/treasurer/loans/active?loan_filter=active'),
      api.get<ApprovedPaymentRequest[]>('/api/payment-requests/?status=approved'),
      api.get<PendingReversal[]>('/api/treasurer/penalties/pending-reversals'),
    ]);

    if (depositsRes.data) setPendingDeposits(depositsRes.data);
    if (penaltiesRes.data) setPendingPenalties(penaltiesRes.data);
    if (loansRes.data) setPendingLoans(loansRes.data);
    if (activeLoansRes.data) {
      setActiveLoans(activeLoansRes.data);
    } else if (activeLoansRes.error) {
      console.error('Active loans fetch error:', activeLoansRes.error);
    }
    if (paymentsRes.data) setApprovedPayments(paymentsRes.data);
    if (reversalsRes.data) setPendingReversals(reversalsRes.data);
    setLoading(false);
  };

  const loadReports = async () => {
    setLoadingReports(true);
    try {
      const [declarationsRes, loansRes, stmtsRes] = await Promise.all([
        api.get<{ month: string; members: DeclarationReportMember[]; total_declared: number; total_deposited: number }>(`/api/treasurer/reports/declarations?month=${selectedReportMonth}`),
        api.get<{ loans: LoanReportItem[]; total_applied: number; total_disbursed: number }>(`/api/treasurer/reports/loans?month=${selectedReportMonth}`),
        api.get<{ statements: BankStatementItem[] }>('/api/treasurer/bank-statements'),
      ]);

      if (declarationsRes.data) {
        setDeclarationsReport(declarationsRes.data.members);
        setTotalDeclared(declarationsRes.data.total_declared ?? 0);
        setTotalDeposited(declarationsRes.data.total_deposited ?? 0);
      }
      if (loansRes.data) {
        setLoansReport(loansRes.data.loans);
        setTotalLoansApplied(loansRes.data.total_applied ?? 0);
        setTotalLoansDisbursed(loansRes.data.total_disbursed ?? 0);
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

  const openRejectDeclaration = (member: DeclarationReportMember) => {
    setRejectTarget(member);
    setRejectDeclComment('');
  };

  const submitRejectDeclaration = async () => {
    if (!rejectTarget?.declaration_id || !rejectDeclComment.trim()) return;
    setRejectingDecl(true);
    try {
      const res = await api.post(
        `/api/chairman/reconcile/declaration/${rejectTarget.declaration_id}/reject`,
        { comment: rejectDeclComment.trim() }
      );
      if (res.error) {
        setMessage({ type: 'error', text: res.error });
      } else {
        setMessage({
          type: 'success',
          text: `Declaration for ${rejectTarget.member_name} rejected. Member can now re-upload proof.`,
        });
        setRejectTarget(null);
        loadReports();
      }
    } finally {
      setRejectingDecl(false);
      setTimeout(() => setMessage(null), 4000);
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
      setLoanApprovalForce(false);
      // Pre-fill override fields with the application's current values so the
      // treasurer can adjust just what they need.
      setApproveAmount(String(loan.amount));
      setApproveTerm(loan.term_months || '1');
      setApproveNote('');
      setApproveSurchargePenaltyId('');
      setShowLoanApprovalModal(true);
      // Load the current penalty-type catalogue so the dropdown reflects
      // whatever the group has configured (e.g. "Emergency Loan K150").
      try {
        const res = await api.get<{ id: string; name: string; description: string | null; fee_amount: string }[]>(
          '/api/treasurer/penalty-types'
        );
        if (res.data && Array.isArray(res.data)) {
          setApprovalPenaltyTypes(res.data);
        }
      } catch {
        // Silent — dropdown just stays empty and treasurer can still approve.
      }
    }
  };

  const confirmApproveLoan = async (force: boolean = false) => {
    if (!loanToApprove) return;

    // Build override body only when the treasurer actually changed something
    // or added a note; otherwise approve with the application's stored values.
    const requestedAmount = parseFloat(approveAmount);
    const body: {
      amount?: number;
      term_months?: string;
      note?: string;
      surcharge_penalty_type_id?: string;
    } = {};
    if (approveSurchargePenaltyId) {
      body.surcharge_penalty_type_id = approveSurchargePenaltyId;
    }
    if (
      !Number.isNaN(requestedAmount) &&
      Math.abs(requestedAmount - Number(loanToApprove.amount)) > 0.001
    ) {
      body.amount = requestedAmount;
    }
    if (approveTerm && approveTerm !== loanToApprove.term_months) {
      body.term_months = approveTerm;
    }
    if (approveNote.trim()) {
      body.note = approveNote.trim();
    }
    // If the amount/term was varied without a note, require one — keeps audit trail clean.
    if ((body.amount !== undefined || body.term_months) && !body.note) {
      setMessage({
        type: 'error',
        text: 'Please add a note explaining the variation from the original application.',
      });
      return;
    }

    setApprovingLoan(loanToApprove.id);
    setMessage(null);
    try {
      const url = `/api/treasurer/loans/${loanToApprove.id}/approve${force ? '?force=true' : ''}`;
      const response = await api.post<{ surcharge_penalty_name?: string | null }>(
        url,
        Object.keys(body).length ? body : undefined,
      );
      if (!response.error) {
        const surchargeName = response.data?.surcharge_penalty_name;
        setMessage({
          type: 'success',
          text: surchargeName
            ? `Loan approved & disbursed. ${surchargeName} penalty also issued — member will see it on their next declaration.`
            : 'Loan approved, disbursed, and posted to member\'s account successfully!',
        });
        await loadData();
        setShowLoanApprovalModal(false);
        setLoanToApprove(null);
      } else {
        // If the backend refused because of the one-active-loan rule but is
        // willing to honor force (backdated application or Admin), surface a
        // second-click "Confirm override" button instead of just an error.
        const refusal = response.error || 'Failed to approve and disburse loan';
        if (
          !force &&
          /already has an active loan/i.test(refusal) &&
          /(force=true|backdated)/i.test(refusal)
        ) {
          setMessage({
            type: 'error',
            text: refusal + ' Click Approve again to confirm the override.',
          });
          // arm the override on the next click
          setLoanApprovalForce(true);
        } else {
          setMessage({ type: 'error', text: refusal });
        }
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

  // Backfill-loan modal helpers
  const openBackfillModal = async () => {
    // Pre-load member list + active cycles the first time
    setBackfillMemberId('');
    setBackfillAmount('');
    setBackfillTerm('1');
    setBackfillRate('');
    setBackfillSuggestedRate(null);
    // Default disbursement date to the 1st of the currently-selected Reports month.
    setBackfillDate(selectedReportMonth);
    setBackfillReason('');
    setBackfillForce(false);
    setBackfillError(null);
    setBackfillErrorField(null);
    setShowBackfillModal(true);
    try {
      const [membersRes, cyclesRes] = await Promise.all([
        api.get<{ id: string; user: { first_name: string; last_name: string } }[]>(
          '/api/chairman/members?status=active',
        ),
        api.get<{ id: string; year: number; cycle_number: number }[]>('/api/member/cycles'),
      ]);
      if (membersRes.data && Array.isArray(membersRes.data)) {
        setBackfillMembers(
          [...membersRes.data].sort((a, b) => {
            const an = `${a.user?.first_name || ''} ${a.user?.last_name || ''}`.trim();
            const bn = `${b.user?.first_name || ''} ${b.user?.last_name || ''}`.trim();
            return an.localeCompare(bn);
          }),
        );
      }
      if (cyclesRes.data && Array.isArray(cyclesRes.data) && cyclesRes.data.length > 0) {
        setBackfillCycles(cyclesRes.data);
        setBackfillCycleId(cyclesRes.data[0].id);
      }
    } catch {
      /* silent — the modal still renders with empty dropdowns */
    }
  };

  const fetchSuggestedRate = async (memberId: string, term: string) => {
    if (!memberId || !term) {
      setBackfillSuggestedRate(null);
      return;
    }
    try {
      const res = await api.get<{ rate: number | null }>(
        `/api/treasurer/members/${memberId}/suggested-loan-rate?term_months=${encodeURIComponent(term)}`,
      );
      const rate = res.data?.rate ?? null;
      setBackfillSuggestedRate(rate);
      // Prefill the rate field with the ACTUAL value (not just a placeholder)
      // so an unedited submit sends the right number. Only overwrite when the
      // field is empty — never clobber a rate the treasurer typed already.
      if (rate != null && backfillRate === '') {
        setBackfillRate(String(rate));
      }
    } catch {
      setBackfillSuggestedRate(null);
    }
  };

  const cancelBackfill = () => {
    setShowBackfillModal(false);
    setBackfillError(null);
    setBackfillErrorField(null);
  };

  const clearBackfillError = () => {
    if (backfillError || backfillErrorField) {
      setBackfillError(null);
      setBackfillErrorField(null);
    }
  };

  const submitBackfill = async () => {
    const raiseFieldError = (
      field: 'member' | 'cycle' | 'amount' | 'term' | 'rate' | 'date' | 'reason',
      msg: string,
    ) => {
      setBackfillError(msg);
      setBackfillErrorField(field);
    };
    if (!backfillMemberId) {
      raiseFieldError('member', 'Pick a member before backfilling.');
      return;
    }
    if (!backfillCycleId) {
      raiseFieldError('cycle', 'Pick a cycle before backfilling.');
      return;
    }
    const amt = parseFloat(backfillAmount);
    if (!amt || amt <= 0) {
      raiseFieldError('amount', 'Loan amount must be greater than zero.');
      return;
    }
    if (!backfillTerm || !backfillTerm.trim()) {
      raiseFieldError('term', 'Term (months) is required.');
      return;
    }
    const rate = parseFloat(backfillRate);
    if (Number.isNaN(rate) || rate < 0) {
      raiseFieldError(
        'rate',
        backfillRate.trim() === ''
          ? 'Interest rate is required — use the current-rate shortcut or type one.'
          : 'Interest rate must be zero or greater.',
      );
      return;
    }
    if (!backfillDate) {
      raiseFieldError('date', 'Pick a disbursement date.');
      return;
    }
    if (backfillDate > new Date().toISOString().slice(0, 10)) {
      raiseFieldError('date', 'Disbursement date cannot be in the future.');
      return;
    }
    if (backfillReason.trim().length < 5) {
      raiseFieldError('reason', 'Reason (min 5 characters) is required for the audit log.');
      return;
    }
    setBackfillSubmitting(true);
    setBackfillError(null);
    setBackfillErrorField(null);
    try {
      const res = await api.post<{ loan_id: string }>('/api/treasurer/loans/backfill', {
        member_id: backfillMemberId,
        cycle_id: backfillCycleId,
        loan_amount: amt,
        term_months: backfillTerm,
        percentage_interest: rate,
        disbursement_date: backfillDate,
        reason: backfillReason.trim(),
        force: backfillForce,
      });
      if (res.error) {
        // Backend refused. Mirror any obvious field mapping.
        const err = res.error;
        if (!backfillForce && /already has an active loan/i.test(err)) {
          setBackfillError(
            err + ' Tick "override active-loan check" below and try again if this is a genuine historical loan.',
          );
        } else if (/loan_amount/i.test(err)) {
          setBackfillErrorField('amount');
          setBackfillError(err);
        } else if (/percentage_interest|interest rate/i.test(err)) {
          setBackfillErrorField('rate');
          setBackfillError(err);
        } else if (/disbursement date/i.test(err)) {
          setBackfillErrorField('date');
          setBackfillError(err);
        } else if (/term_months/i.test(err)) {
          setBackfillErrorField('term');
          setBackfillError(err);
        } else if (/reason/i.test(err)) {
          setBackfillErrorField('reason');
          setBackfillError(err);
        } else {
          setBackfillError(err);
        }
      } else {
        setMessage({
          type: 'success',
          text: `Historical loan recorded (${res.data?.loan_id?.slice(0, 8)}). It will appear in the Loans report for the selected month.`,
        });
        setShowBackfillModal(false);
        setBackfillError(null);
        setBackfillErrorField(null);
        await loadReports();
        await loadData();
        setTimeout(() => setMessage(null), 6000);
      }
    } catch (err: any) {
      setBackfillError(err?.message || 'Failed to record loan');
    } finally {
      setBackfillSubmitting(false);
    }
  };

  // Move-disbursement-month modal helpers
  const openMoveLoan = (loan: LoanReportItem) => {
    setMoveLoan(loan);
    // Default to the first of the currently-viewed report month so a click on
    // a loan in the "wrong month" pre-fills to the "right month" the treasurer
    // is looking at.
    setMoveLoanNewDate(selectedReportMonth);
    setMoveLoanReason('');
    setMoveLoanError(null);
    setMoveLoanErrorField(null);
  };

  const cancelMoveLoan = () => {
    setMoveLoan(null);
    setMoveLoanNewDate('');
    setMoveLoanReason('');
    setMoveLoanError(null);
    setMoveLoanErrorField(null);
  };

  const clearMoveLoanError = () => {
    if (moveLoanError || moveLoanErrorField) {
      setMoveLoanError(null);
      setMoveLoanErrorField(null);
    }
  };

  const submitMoveLoan = async () => {
    if (!moveLoan) return;
    if (!moveLoanNewDate) {
      setMoveLoanError('Pick a new disbursement date.');
      setMoveLoanErrorField('date');
      return;
    }
    if (moveLoanNewDate > new Date().toISOString().slice(0, 10)) {
      setMoveLoanError('Disbursement date cannot be in the future.');
      setMoveLoanErrorField('date');
      return;
    }
    if (moveLoanReason.trim().length < 5) {
      setMoveLoanError('Reason (min 5 characters) is required for the audit log.');
      setMoveLoanErrorField('reason');
      return;
    }
    setMoveLoanSubmitting(true);
    setMoveLoanError(null);
    setMoveLoanErrorField(null);
    try {
      const res = await api.post(
        `/api/treasurer/loans/${moveLoan.loan_id}/move-disbursement-date`,
        {
          new_disbursement_date: moveLoanNewDate,
          reason: moveLoanReason.trim(),
        },
      );
      if (res.error) {
        setMoveLoanError(res.error);
        if (/disbursement date/i.test(res.error)) setMoveLoanErrorField('date');
        else if (/reason/i.test(res.error)) setMoveLoanErrorField('reason');
      } else {
        setMessage({ type: 'success', text: 'Loan disbursement date moved.' });
        setMoveLoan(null);
        await loadReports();
        setTimeout(() => setMessage(null), 5000);
      }
    } catch (err: any) {
      setMoveLoanError(err?.message || 'Failed to move loan');
    } finally {
      setMoveLoanSubmitting(false);
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
        <div className="mb-4 flex flex-wrap gap-3">
          <Link
            href="/dashboard/reconcile"
            className="inline-flex items-center px-4 py-2 bg-gradient-to-br from-blue-500 to-blue-600 border-2 border-blue-600 text-white rounded-lg font-semibold text-sm hover:from-blue-600 hover:to-blue-700 transition-all"
          >
            Reconciliation
          </Link>
          <Link
            href="/dashboard/treasurer/reports/interest-revenue"
            className="inline-flex items-center px-4 py-2 bg-gradient-to-br from-emerald-500 to-emerald-600 border-2 border-emerald-600 text-white rounded-lg font-semibold text-sm hover:from-emerald-600 hover:to-emerald-700 transition-all"
          >
            Loan/Revenue Report
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
                  {(showAllDeposits ? pendingDeposits : pendingDeposits.slice(0, 3)).map((deposit) => (
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
                    <button
                      onClick={() => setShowAllDeposits((v) => !v)}
                      className="block mx-auto text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline pt-2 focus:outline-none"
                    >
                      {showAllDeposits ? 'Show less' : `+${pendingDeposits.length - 3} more`}
                    </button>
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
                  {(showAllPendingLoans ? pendingLoans : pendingLoans.slice(0, 3)).map((loan) => (
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
                    <button
                      onClick={() => setShowAllPendingLoans((v) => !v)}
                      className="block mx-auto text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline pt-2 focus:outline-none"
                    >
                      {showAllPendingLoans ? 'Show less' : `+${pendingLoans.length - 3} more`}
                    </button>
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
              <div className="flex gap-2 mb-3 flex-wrap">
                {([
                  { key: 'active',     label: 'Active',     activeColor: 'bg-blue-600 border-blue-600',     idleColor: 'text-blue-700 border-blue-300 hover:bg-blue-50' },
                  { key: 'at_risk',    label: 'At Risk',    activeColor: 'bg-amber-500 border-amber-500',   idleColor: 'text-amber-700 border-amber-300 hover:bg-amber-50' },
                  { key: 'defaulting', label: 'Defaulting', activeColor: 'bg-red-600 border-red-600',       idleColor: 'text-red-700 border-red-300 hover:bg-red-50' },
                  { key: 'paid',       label: 'Paid Off',   activeColor: 'bg-green-600 border-green-600',   idleColor: 'text-green-700 border-green-300 hover:bg-green-50' },
                ] as const).map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => {
                      if (loanFilter !== opt.key) {
                        setLoanFilter(opt.key);
                        setShowAllLoans(false);
                        loadLoans(opt.key);
                      }
                    }}
                    className={`flex-1 min-w-[80px] py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                      loanFilter === opt.key
                        ? `${opt.activeColor} text-white`
                        : `bg-white ${opt.idleColor}`
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {/* Name search */}
              <div className="mb-3 relative">
                <input
                  type="text"
                  value={loanNameQuery}
                  onChange={(e) => {
                    setLoanNameQuery(e.target.value);
                    setShowAllLoans(false);
                  }}
                  placeholder="Filter by first or last name…"
                  className="w-full px-3 py-2 pr-8 text-sm border-2 border-blue-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-blue-400"
                />
                {loanNameQuery && (
                  <button
                    type="button"
                    onClick={() => setLoanNameQuery('')}
                    aria-label="Clear name filter"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-blue-400 hover:text-blue-700 text-sm"
                  >
                    ×
                  </button>
                )}
              </div>

              {(() => {
                const q = loanNameQuery.trim().toLowerCase();
                const filteredLoans = q
                  ? activeLoans.filter((l) =>
                      (l.member_name || '').toLowerCase().includes(q),
                    )
                  : activeLoans;
                if (filteredLoans.length === 0) {
                  return (
                    <p className="text-blue-700 text-sm text-center py-6">
                      {q
                        ? `No loans matching "${loanNameQuery}"`
                        : loanFilter === 'paid'
                          ? 'No paid-off loans'
                          : loanFilter === 'at_risk'
                            ? 'No at-risk loans'
                            : loanFilter === 'defaulting'
                              ? 'No defaulting loans'
                              : 'No active loans'}
                    </p>
                  );
                }
                return (
                <div className="space-y-2 max-h-[460px] overflow-y-auto">
                  {(showAllLoans ? filteredLoans : filteredLoans.slice(0, 3)).map((loan) => (
                    <div
                      key={loan.id}
                      className="p-3 bg-gradient-to-r from-green-50 to-green-100 border-2 border-green-300 rounded-lg hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => handleViewLoanDetails(loan.id)}
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1.5">
                            <p className="font-semibold text-sm text-blue-900 truncate">
                              {loan.member_name}
                            </p>
                            {loan.performance_status === 'defaulting' && (
                              <span className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide rounded bg-red-600 text-white whitespace-nowrap">
                                Defaulting
                              </span>
                            )}
                            {loan.performance_status === 'at_risk' && (
                              <span className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide rounded bg-amber-500 text-white whitespace-nowrap">
                                At Risk
                              </span>
                            )}
                          </div>
                          <div className="space-y-0.5">
                            {loan.disbursement_date && (
                              <div className="flex justify-between text-xs">
                                <span className="text-gray-500">Borrowed</span>
                                <span className="font-medium text-gray-700">
                                  {new Date(loan.disbursement_date + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                                </span>
                              </div>
                            )}
                            {loan.maturity_date && (
                              <div className="flex justify-between text-xs">
                                <span className="text-gray-500">Maturity</span>
                                <span className="font-medium text-gray-700">
                                  {new Date(loan.maturity_date + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                                </span>
                              </div>
                            )}
                            <div className="flex justify-between text-xs">
                              <span className="text-blue-500">Principal Amount</span>
                              <span className="font-semibold text-blue-900">K{loan.loan_amount.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-green-600">Principal Paid</span>
                              <span className="font-semibold text-green-800">K{loan.total_principal_paid.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-orange-500">
                                Interest on Loan{loan.interest_rate
                                  ? ` (${loan.interest_rate}%${loan.term_months !== 'N/A' ? `, ${loan.term_months}m` : ''})`
                                  : ''}
                              </span>
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
                  {filteredLoans.length > 3 && (
                    <button
                      onClick={() => setShowAllLoans(prev => !prev)}
                      className="w-full text-xs text-blue-600 font-semibold text-center pt-2 hover:text-blue-800 transition-colors"
                    >
                      {showAllLoans
                        ? 'Show less'
                        : `+${filteredLoans.length - 3} more`}
                    </button>
                  )}
                </div>
                );
              })()}
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
                  {(showAllPenalties ? pendingPenalties : pendingPenalties.slice(0, 3)).map((penalty) => (
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
                    <button
                      onClick={() => setShowAllPenalties((v) => !v)}
                      className="block mx-auto text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline pt-2 focus:outline-none"
                    >
                      {showAllPenalties ? 'Show less' : `+${pendingPenalties.length - 3} more`}
                    </button>
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
                      <div className="flex gap-4 mb-3 text-xs">
                        <div className="flex-1 bg-blue-50 rounded-lg px-3 py-2">
                          <span className="text-blue-600">Total Declared</span>
                          <p className="text-blue-900 font-bold text-sm">K{totalDeclared.toLocaleString()}</p>
                        </div>
                        <div className="flex-1 bg-green-50 rounded-lg px-3 py-2">
                          <span className="text-green-600">Total Deposited</span>
                          <p className="text-green-900 font-bold text-sm">K{totalDeposited.toLocaleString()}</p>
                        </div>
                      </div>
                      {/* Provenance legend */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 px-2 py-1.5 mb-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-900">
                        <span className="font-semibold">Legend:</span>
                        <span title="A real proof of payment file was uploaded"><span className="font-bold">📎</span> Proof attached</span>
                        <span title="Declaration was created by the treasurer via reconciliation"><span className="font-bold">♻️</span> Created via reconciliation</span>
                        <span title="Approved via a reconciliation entry (no physical proof file)"><span className="font-bold">⚙️</span> Approved via reconciliation</span>
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
                                {member.is_phantom ? (
                                  <span
                                    className="text-amber-700"
                                    title="Empty reconciliation was saved — declaration is marked approved with K0. Reject to clean it up."
                                  >
                                    K0 ⚠
                                  </span>
                                ) : member.declaration_amount != null ? (
                                  `K${member.declaration_amount.toLocaleString()}`
                                ) : null}
                                {member.is_paid && (
                                  <>
                                    {!member.is_phantom && (
                                      <span className="inline-flex items-center justify-center w-5 h-5 bg-green-500 rounded text-white text-xs font-bold">✓</span>
                                    )}
                                    {member.has_real_proof && (
                                      <span title="Proof of payment file is attached" className="text-base leading-none">📎</span>
                                    )}
                                    {member.created_via_reconciliation && (
                                      <span title="Created by the treasurer via reconciliation" className="text-base leading-none">♻️</span>
                                    )}
                                    {member.approved_via_reconciliation && (
                                      <span title="Approved via reconciliation (no physical proof file)" className="text-base leading-none">⚙️</span>
                                    )}
                                    {member.declaration_id && (
                                      <button
                                        type="button"
                                        onClick={() => openRejectDeclaration(member)}
                                        title={
                                          member.is_phantom
                                            ? 'Phantom approved declaration — reject to clear and let the member re-declare'
                                            : 'Reverse this declaration and let the member re-upload proof'
                                        }
                                        className="ml-1 px-1.5 py-0.5 text-xs font-semibold text-red-700 bg-red-50 hover:bg-red-100 border border-red-300 rounded transition-colors"
                                      >
                                        Reject
                                      </button>
                                    )}
                                  </>
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
                        <div className="flex items-center gap-2">
                          <button
                            onClick={openBackfillModal}
                            title="Record a historical loan disbursed off-system"
                            className="px-2 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition-colors"
                          >
                            + Backfill Loan
                          </button>
                          <button
                            onClick={copyLoansReport}
                            className="px-2 py-1 bg-green-600 text-white rounded text-xs font-semibold hover:bg-green-700 transition-colors"
                          >
                            Copy
                          </button>
                        </div>
                      </div>
                      <div className="flex gap-4 mb-3 text-xs">
                        <div className="flex-1 bg-green-50 rounded-lg px-3 py-2">
                          <span className="text-green-600">Total Applied</span>
                          <p className="text-green-900 font-bold text-sm">K{totalLoansApplied.toLocaleString()}</p>
                        </div>
                        <div className="flex-1 bg-green-50 rounded-lg px-3 py-2">
                          <span className="text-green-600">Total Disbursed</span>
                          <p className="text-green-900 font-bold text-sm">K{totalLoansDisbursed.toLocaleString()}</p>
                        </div>
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
                              {loan.is_approved && (
                                <button
                                  type="button"
                                  onClick={() => openMoveLoan(loan)}
                                  title="Move this loan's disbursement month (also re-buckets the ledger entry)"
                                  className="text-[11px] text-blue-600 hover:text-blue-800 hover:underline font-sans font-semibold"
                                >
                                  Move month
                                </button>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Pending Penalty Reversals */}
                {pendingReversals.length > 0 && (
                  <div className="bg-white border-2 border-orange-200 rounded-lg p-4">
                    <h3 className="text-base font-bold text-orange-900 mb-3">
                      Pending Penalty Reversals ({pendingReversals.length})
                    </h3>
                    <div className="space-y-2 max-h-[400px] overflow-y-auto">
                      {pendingReversals.map(r => (
                        <div key={r.id} className="border border-orange-100 rounded-lg p-3 bg-orange-50">
                          <div className="flex justify-between items-start gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <span className="font-semibold text-orange-900">{r.member_name}</span>
                                <span className="text-xs bg-orange-200 text-orange-800 px-2 py-0.5 rounded-full">{r.penalty_type_name}</span>
                                <span className="font-bold text-orange-900">K{r.fee_amount.toLocaleString()}</span>
                              </div>
                              <p className="text-sm text-red-700 font-medium">Reason: {r.reversal_reason}</p>
                              {r.notes && <p className="text-xs text-orange-600 mt-0.5">Original note: {r.notes}</p>}
                              <p className="text-xs text-orange-500 mt-0.5">
                                Requested by {r.reversal_requested_by_name || 'Unknown'}
                                {r.reversal_requested_at && ` on ${new Date(r.reversal_requested_at).toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}`}
                              </p>
                            </div>
                            <button
                              disabled={approvingReversalId === r.id}
                              onClick={async () => {
                                setApprovingReversalId(r.id);
                                const res = await api.post(`/api/treasurer/penalties/${r.id}/approve-reversal`, {});
                                setApprovingReversalId(null);
                                if (res.data) {
                                  loadData();
                                }
                              }}
                              className="px-3 py-1.5 bg-orange-600 text-white rounded-lg text-xs font-semibold hover:bg-orange-700 disabled:opacity-50 shrink-0"
                            >
                              {approvingReversalId === r.id ? 'Reversing...' : 'Approve Reversal'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Approved Payment Requests */}
                {approvedPayments.length > 0 && (
                  <div className="bg-white border-2 border-green-200 rounded-lg p-4">
                    <h3 className="text-base font-bold text-green-900 mb-3">
                      Approved Payment Requests ({approvedPayments.length})
                    </h3>
                    <div className="space-y-2 max-h-[400px] overflow-y-auto">
                      {approvedPayments.map(pr => (
                        <div key={pr.id} className="border border-green-100 rounded-lg p-3 bg-green-50">
                          <div className="flex justify-between items-start gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-base font-bold text-green-900">
                                  K{pr.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                                <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">
                                  {pr.source_account_code === 'ADMIN_FUND' ? 'Admin Fund'
                                    : pr.source_account_code === 'SOCIAL_FUND' ? 'Social Fund'
                                    : pr.source_account_code === 'INTEREST_INCOME' ? 'Savings + Interest'
                                    : pr.source_account_code === 'PENALTY_INCOME' ? 'Penalties'
                                    : pr.source_account_code}
                                </span>
                              </div>
                              <p className="text-sm text-green-800">{pr.description}</p>
                              <p className="text-xs text-green-600 mt-0.5">
                                Paid to: <span className="font-semibold">{pr.beneficiary_name}</span>
                              </p>
                              <p className="text-xs text-green-500">
                                Approved by {pr.approver_name || 'Chairman'}
                                {pr.approved_at && ` on ${new Date(pr.approved_at).toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}`}
                              </p>
                            </div>
                            <button
                              onClick={() => { setExecutingPaymentId(pr.id); setPaymentReference(''); }}
                              className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700 transition-colors shrink-0"
                            >
                              Execute
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Execute Payment Modal */}
                {executingPaymentId && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
                      <h3 className="text-lg font-bold text-green-900 mb-3">Execute Payment</h3>
                      <p className="text-sm text-blue-700 mb-4">
                        This will deduct the amount from the source account and record the journal entry.
                      </p>
                      <div className="mb-4">
                        <label className="block text-sm font-semibold text-blue-900 mb-1">Payment Reference (optional)</label>
                        <input
                          type="text"
                          value={paymentReference}
                          onChange={e => setPaymentReference(e.target.value)}
                          className="w-full"
                          placeholder="Bank reference, receipt number..."
                          autoFocus
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setExecutingPaymentId(null)}
                          className="px-4 py-2 bg-gray-200 rounded-lg text-sm font-semibold"
                        >
                          Cancel
                        </button>
                        <button
                          disabled={executingPayment}
                          onClick={async () => {
                            setExecutingPayment(true);
                            const res = await api.put(`/api/payment-requests/${executingPaymentId}/execute`, {
                              payment_reference: paymentReference || null,
                            });
                            setExecutingPayment(false);
                            if (res.data) {
                              setExecutingPaymentId(null);
                              loadData();
                            }
                          }}
                          className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors"
                        >
                          {executingPayment ? 'Processing...' : 'Confirm & Execute'}
                        </button>
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
                      {bankStatements.map((stmt, index) => {
                        const isEditing = inlineEditStmtId === stmt.id;
                        if (!isEditing) {
                          return (
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
                                onClick={() => startInlineEditStmt(stmt)}
                                className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs font-semibold hover:bg-gray-200 transition-colors flex-shrink-0"
                              >
                                Edit
                              </button>
                            </div>
                          );
                        }
                        return (
                          <div
                            key={stmt.id}
                            className="rounded-lg border-2 border-purple-300 bg-purple-50/50 p-3 space-y-2 text-sm"
                          >
                            <div className="flex items-center gap-2 text-xs font-semibold text-purple-700">
                              <span className="w-6 text-right">{String(index + 1).padStart(2, ' ')}.</span>
                              <span>Editing — {formatMonth(stmt.statement_month)} (current)</span>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              <label className="flex flex-col gap-1">
                                <span className="text-xs font-semibold text-purple-700">Month</span>
                                <input
                                  type="month"
                                  value={inlineStmtMonth}
                                  onChange={(e) => setInlineStmtMonth(e.target.value)}
                                  className="px-2 py-1 border-2 border-purple-300 rounded text-sm"
                                />
                              </label>
                              <label className="flex flex-col gap-1">
                                <span className="text-xs font-semibold text-purple-700">Description</span>
                                <input
                                  type="text"
                                  value={inlineStmtDesc}
                                  onChange={(e) => setInlineStmtDesc(e.target.value)}
                                  placeholder="e.g. 05 May to 10 June"
                                  className="px-2 py-1 border-2 border-purple-300 rounded text-sm"
                                />
                              </label>
                            </div>
                            <label className="flex flex-col gap-1">
                              <span className="text-xs font-semibold text-purple-700">
                                Replace file (optional)
                              </span>
                              <input
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png"
                                onChange={(e) => setInlineStmtFile(e.target.files?.[0] ?? null)}
                                className="text-xs"
                              />
                              <span className="text-[11px] text-purple-600">
                                Leave empty to keep the existing file.
                                {stmt.filename && <> Current: <span className="font-mono">{stmt.filename}</span></>}
                              </span>
                            </label>
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={cancelInlineEditStmt}
                                disabled={inlineStmtSaving}
                                className="px-3 py-1 text-xs font-semibold text-gray-700 hover:text-gray-900"
                              >
                                Cancel
                              </button>
                              <button
                                onClick={() => saveInlineEditStmt(stmt.id)}
                                disabled={inlineStmtSaving}
                                className="px-3 py-1 bg-purple-600 text-white rounded text-xs font-semibold hover:bg-purple-700 disabled:opacity-50"
                              >
                                {inlineStmtSaving ? 'Saving…' : 'Save changes'}
                              </button>
                            </div>
                          </div>
                        );
                      })}
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

      {/* Proof of Payment Modal — stacks above Declaration Details (z-50) so
          it stays on top when opened from inside that modal. */}
      {showProofModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-[60]" onClick={closeProofModal}>
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
                        {selectedLoan.interest_rate
                          ? ` (${selectedLoan.interest_rate}% of principal${selectedLoan.term_months !== 'N/A' ? `, ${selectedLoan.term_months} months` : ''})`
                          : ''}
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

      {/* Reject Declaration Modal */}
      {rejectTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6 space-y-4">
            <h2 className="text-lg font-bold text-red-700">Reject Declaration</h2>
            <p className="text-sm text-gray-700">
              You are about to reverse the <strong>{formatMonth(selectedReportMonth)}</strong> declaration
              for <strong>{rejectTarget.member_name}</strong> (K{rejectTarget.declaration_amount?.toLocaleString()}).
            </p>
            <ul className="text-sm text-gray-700 list-disc pl-5 space-y-1">
              <li>All ledger postings for this deposit (savings, social, admin, penalties, interest, loan repayment) will be reversed.</li>
              <li>The deposit proof will be marked <em>rejected</em> with your comment, and the declaration set back to <em>pending</em>.</li>
              <li>The member can then edit the declaration and re-upload proof normally.</li>
            </ul>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-semibold text-blue-900">
                Comment to member (required)
              </label>
              <textarea
                value={rejectDeclComment}
                onChange={(e) => setRejectDeclComment(e.target.value)}
                rows={3}
                placeholder="e.g. Proof of payment was not actually submitted — please attach the deposit slip and resubmit."
                className="px-3 py-2 border-2 border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setRejectTarget(null)}
                disabled={rejectingDecl}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={submitRejectDeclaration}
                disabled={rejectingDecl || !rejectDeclComment.trim()}
                className="px-5 py-2 bg-red-600 text-white rounded-lg font-semibold text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {rejectingDecl ? 'Rejecting…' : 'Reject Declaration'}
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
                      {declarationDetails.deposit_proof ? (
                        <div className="bg-gray-50 border-2 border-gray-200 rounded-xl p-4">
                          <h3 className="font-bold text-lg text-gray-900 mb-2">Deposit Proof</h3>
                          <div className="space-y-1 text-sm">
                            <p><span className="font-medium text-gray-700">Status:</span> {declarationDetails.deposit_proof.status}</p>
                            <p><span className="font-medium text-gray-700">Amount:</span> K{declarationDetails.deposit_proof.amount.toLocaleString()}</p>
                            {declarationDetails.deposit_proof.uploaded_at && (
                              <p><span className="font-medium text-gray-700">Uploaded:</span> {new Date(declarationDetails.deposit_proof.uploaded_at).toLocaleString()}</p>
                            )}
                          </div>
                          <div className="mt-3">
                            {declarationDetails.deposit_proof.has_file && declarationDetails.deposit_proof.upload_path ? (
                              <button
                                type="button"
                                onClick={() => handleViewProof(
                                  declarationDetails.deposit_proof!.upload_path!,
                                  { upload_path: declarationDetails.deposit_proof!.upload_path! } as PendingDeposit,
                                )}
                                className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 transition-colors"
                              >
                                📎 View Proof of Payment
                              </button>
                            ) : (
                              <p className="text-sm italic text-amber-700 bg-amber-50 border border-amber-300 rounded px-3 py-2">
                                No proof of payment was uploaded — this entry was created via reconciliation.
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="bg-gray-50 border-2 border-gray-200 rounded-xl p-4">
                          <h3 className="font-bold text-lg text-gray-900 mb-2">Deposit Proof</h3>
                          <p className="text-sm italic text-amber-700 bg-amber-50 border border-amber-300 rounded px-3 py-2">
                            No proof of payment was uploaded for this declaration.
                          </p>
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
            className="bg-white rounded-xl shadow-2xl max-w-md w-full max-h-[90vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-green-600 text-white px-6 py-4 rounded-t-xl shrink-0">
              <h2 className="text-xl md:text-2xl font-bold">Confirm Loan Approval</h2>
            </div>

            <div className="flex-1 overflow-y-auto p-6 md:p-8">
              <div>
                <p className="text-base md:text-lg text-blue-900 mb-4">
                  Are you sure you want to approve and disburse this loan?
                </p>
                <div className="bg-blue-50 border-2 border-blue-200 rounded-xl p-4 space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-blue-700 font-medium">Member:</span>
                    <span className="text-sm text-blue-900 font-semibold">{loanToApprove.member_name}</span>
                  </div>
                  <div className="flex justify-between text-xs text-blue-700">
                    <span>Member requested:</span>
                    <span>
                      K{loanToApprove.amount.toLocaleString()} ·{' '}
                      {loanToApprove.term_months} {loanToApprove.term_months === '1' ? 'Month' : 'Months'}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-blue-900">
                        Disburse Amount (K)
                      </label>
                      <input
                        type="number" inputMode="decimal"
                        step="0.01"
                        min="0"
                        value={approveAmount}
                        onChange={(e) => setApproveAmount(e.target.value)}
                        className="px-3 py-2 border-2 border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-blue-900">Term (months)</label>
                      <input
                        type="text"
                        value={approveTerm}
                        onChange={(e) => setApproveTerm(e.target.value)}
                        className="px-3 py-2 border-2 border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">
                      Note (required if amount or term varies)
                    </label>
                    <textarea
                      rows={2}
                      value={approveNote}
                      onChange={(e) => setApproveNote(e.target.value)}
                      placeholder="e.g. Group only has K7,000 cash on hand; disbursing K7,000 of the K10,000 requested."
                      className="px-3 py-2 border-2 border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">
                      Surcharge penalty (optional)
                    </label>
                    <select
                      value={approveSurchargePenaltyId}
                      onChange={(e) => setApproveSurchargePenaltyId(e.target.value)}
                      className="px-3 py-2 border-2 border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="">None — standard loan</option>
                      {approvalPenaltyTypes.map((pt) => (
                        <option key={pt.id} value={pt.id}>
                          {pt.name} — K{Number(pt.fee_amount).toLocaleString()}
                        </option>
                      ))}
                    </select>
                    {approveSurchargePenaltyId && (() => {
                      const pt = approvalPenaltyTypes.find((p) => p.id === approveSurchargePenaltyId);
                      if (!pt) return null;
                      return (
                        <p className="text-[11px] text-amber-700 mt-0.5">
                          Member will see a pending K{Number(pt.fee_amount).toLocaleString()}{' '}
                          <span className="font-semibold">{pt.name}</span> penalty on their next declaration.
                          {pt.description ? ` (${pt.description})` : ''}
                        </p>
                      );
                    })()}
                  </div>
                </div>
                <div className="mt-4 p-3 bg-yellow-50 border-2 border-yellow-300 rounded-xl">
                  <p className="text-sm text-yellow-800 font-medium">
                    ⚠️ This will post the loan to the member&apos;s account and make it active. The
                    application record will be updated to reflect the disbursed amount/term and your note.
                  </p>
                </div>
              </div>
            </div>

            <div className="shrink-0 flex flex-col sm:flex-row justify-end gap-3 p-4 md:p-6 border-t-2 border-gray-200 bg-white">
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
                onClick={() => confirmApproveLoan(loanApprovalForce)}
                disabled={approvingLoan === loanToApprove.id}
                className={`px-4 py-2 md:px-6 md:py-3 border-2 text-white rounded-xl disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold transition-all duration-200 ${
                  loanApprovalForce
                    ? 'bg-gradient-to-br from-amber-500 to-amber-600 border-amber-600 hover:from-amber-600 hover:to-amber-700'
                    : 'bg-gradient-to-br from-green-500 to-green-600 border-green-600 hover:from-green-600 hover:to-green-700'
                }`}
              >
                {approvingLoan === loanToApprove.id
                  ? 'Approving...'
                  : loanApprovalForce
                    ? 'Confirm Override & Disburse'
                    : 'Approve & Disburse Loan'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Backfill Loan Modal — record a historical loan disbursed off-system */}
      {showBackfillModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={cancelBackfill}>
          <div
            className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl shrink-0">
              <h2 className="text-xl md:text-2xl font-bold">Backfill Historical Loan</h2>
              <p className="text-xs text-blue-100 mt-1">
                Record a loan the group disbursed off-system so its repayments can be reconciled.
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {backfillError && (
                <div
                  role="alert"
                  className="p-3 bg-red-50 border-2 border-red-400 rounded-xl flex items-start gap-2"
                >
                  <span className="text-red-600 text-lg leading-none">⚠</span>
                  <p className="text-sm text-red-800 font-medium flex-1">{backfillError}</p>
                  <button
                    type="button"
                    onClick={clearBackfillError}
                    className="text-red-500 hover:text-red-700 text-xl leading-none"
                    aria-label="Dismiss error"
                  >
                    ×
                  </button>
                </div>
              )}
              <div className="grid grid-cols-1 gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-blue-900">Member</label>
                  <select
                    value={backfillMemberId}
                    onChange={(e) => {
                      clearBackfillError();
                      setBackfillMemberId(e.target.value);
                      fetchSuggestedRate(e.target.value, backfillTerm);
                    }}
                    className={`px-3 py-2 border-2 rounded text-sm bg-white ${
                      backfillErrorField === 'member' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                    }`}
                  >
                    <option value="">Pick a member…</option>
                    {backfillMembers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {`${m.user?.first_name || ''} ${m.user?.last_name || ''}`.trim() || m.id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-blue-900">Cycle</label>
                  <select
                    value={backfillCycleId}
                    onChange={(e) => {
                      clearBackfillError();
                      setBackfillCycleId(e.target.value);
                    }}
                    className={`px-3 py-2 border-2 rounded text-sm bg-white ${
                      backfillErrorField === 'cycle' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                    }`}
                  >
                    {backfillCycles.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.year} — Cycle {c.cycle_number}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">Loan amount (K)</label>
                    <input
                      type="number" inputMode="decimal"
                      min="0"
                      step="0.01"
                      value={backfillAmount}
                      onChange={(e) => {
                        clearBackfillError();
                        setBackfillAmount(e.target.value);
                      }}
                      className={`px-3 py-2 border-2 rounded text-sm ${
                        backfillErrorField === 'amount' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                      }`}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">Term (months)</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={backfillTerm}
                      onChange={(e) => {
                        clearBackfillError();
                        setBackfillTerm(e.target.value);
                        fetchSuggestedRate(backfillMemberId, e.target.value);
                      }}
                      className={`px-3 py-2 border-2 rounded text-sm ${
                        backfillErrorField === 'term' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                      }`}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">Interest rate (%)</label>
                    <input
                      type="number" inputMode="decimal"
                      min="0"
                      step="0.01"
                      value={backfillRate}
                      onChange={(e) => {
                        clearBackfillError();
                        setBackfillRate(e.target.value);
                      }}
                      className={`px-3 py-2 border-2 rounded text-sm ${
                        backfillErrorField === 'rate' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                      }`}
                      placeholder="e.g. 6"
                    />
                    {backfillSuggestedRate != null ? (
                      <p className="text-[11px] text-blue-700">
                        Prefilled from current rate ({backfillSuggestedRate}%). Edit if the historical rate was different.
                      </p>
                    ) : backfillMemberId ? (
                      <p className="text-[11px] text-amber-700">
                        No current rate configured for this member × term — type the historical rate.
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-blue-900">Disbursement date</label>
                    <input
                      type="date"
                      max={new Date().toISOString().slice(0, 10)}
                      value={backfillDate}
                      onChange={(e) => {
                        clearBackfillError();
                        setBackfillDate(e.target.value);
                      }}
                      className={`px-3 py-2 border-2 rounded text-sm ${
                        backfillErrorField === 'date' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                      }`}
                    />
                    <p className="text-[11px] text-gray-500">Sets both the loan date and the ledger dealing month.</p>
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-blue-900">Reason (required, audit logged)</label>
                  <textarea
                    rows={2}
                    value={backfillReason}
                    onChange={(e) => {
                      clearBackfillError();
                      setBackfillReason(e.target.value);
                    }}
                    placeholder="e.g. Loan issued to member in April 2026 outside the system; repayments already declared."
                    className={`px-3 py-2 border-2 rounded text-sm ${
                      backfillErrorField === 'reason' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                    }`}
                  />
                </div>
                <label className="flex items-start gap-2 text-xs text-blue-900">
                  <input
                    type="checkbox"
                    checked={backfillForce}
                    onChange={(e) => setBackfillForce(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    Override active-loan check (only tick when the member has a separate current loan that isn&apos;t this historical one).
                  </span>
                </label>
              </div>
              <div className="p-3 bg-yellow-50 border-2 border-yellow-300 rounded-xl">
                <p className="text-xs text-yellow-800 font-medium">
                  ⚠️ This posts the disbursement JE to the ledger under the chosen date&apos;s dealing month. Interest is recognised at origination. Reconciliation will then let you allocate existing repayments against this loan.
                </p>
              </div>
            </div>
            <div className="shrink-0 flex flex-col sm:flex-row justify-end gap-3 p-4 md:p-6 border-t-2 border-gray-200 bg-white">
              <button type="button" onClick={cancelBackfill} disabled={backfillSubmitting} className="btn-secondary disabled:opacity-50">
                Cancel
              </button>
              <button
                type="button"
                onClick={submitBackfill}
                disabled={backfillSubmitting}
                className="px-4 py-2 md:px-6 md:py-3 bg-blue-600 border-2 border-blue-700 text-white rounded-xl disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold hover:bg-blue-700"
              >
                {backfillSubmitting ? 'Recording…' : 'Record & Disburse Loan'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Move-loan-month modal — retiming a loan onto the correct month */}
      {moveLoan && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={cancelMoveLoan}>
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full max-h-[90vh] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl shrink-0">
              <h2 className="text-xl md:text-2xl font-bold">Move Loan to Different Month</h2>
              <p className="text-xs text-blue-100 mt-1">
                {moveLoan.member_name} · K{moveLoan.loan_amount.toLocaleString()} (loan {moveLoan.loan_id.slice(0, 8)})
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {moveLoanError && (
                <div
                  role="alert"
                  className="p-3 bg-red-50 border-2 border-red-400 rounded-xl flex items-start gap-2"
                >
                  <span className="text-red-600 text-lg leading-none">⚠</span>
                  <p className="text-sm text-red-800 font-medium flex-1">{moveLoanError}</p>
                  <button
                    type="button"
                    onClick={clearMoveLoanError}
                    className="text-red-500 hover:text-red-700 text-xl leading-none"
                    aria-label="Dismiss error"
                  >
                    ×
                  </button>
                </div>
              )}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">New disbursement date</label>
                <input
                  type="date"
                  max={new Date().toISOString().slice(0, 10)}
                  value={moveLoanNewDate}
                  onChange={(e) => {
                    clearMoveLoanError();
                    setMoveLoanNewDate(e.target.value);
                  }}
                  className={`px-3 py-2 border-2 rounded text-sm ${
                    moveLoanErrorField === 'date' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                  }`}
                />
                <p className="text-[11px] text-gray-500">
                  Both the loan date and the ledger dealing month update. Repayment dates on this loan aren&apos;t touched.
                </p>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">Reason (required, audit logged)</label>
                <textarea
                  rows={2}
                  value={moveLoanReason}
                  onChange={(e) => {
                    clearMoveLoanError();
                    setMoveLoanReason(e.target.value);
                  }}
                  placeholder="e.g. Disbursed in April but posted to May by mistake."
                  className={`px-3 py-2 border-2 rounded text-sm ${
                    moveLoanErrorField === 'reason' ? 'border-red-500 focus:border-red-500 focus:ring-red-400' : 'border-blue-300'
                  }`}
                />
              </div>
            </div>
            <div className="shrink-0 flex flex-col sm:flex-row justify-end gap-3 p-4 md:p-6 border-t-2 border-gray-200 bg-white">
              <button type="button" onClick={cancelMoveLoan} disabled={moveLoanSubmitting} className="btn-secondary disabled:opacity-50">
                Cancel
              </button>
              <button
                type="button"
                onClick={submitMoveLoan}
                disabled={moveLoanSubmitting}
                className="px-4 py-2 md:px-6 md:py-3 bg-blue-600 border-2 border-blue-700 text-white rounded-xl disabled:opacity-50 disabled:cursor-not-allowed text-sm md:text-base font-semibold hover:bg-blue-700"
              >
                {moveLoanSubmitting ? 'Moving…' : 'Move Loan'}
              </button>
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
