'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface PaymentRequest {
  id: string;
  amount: number;
  description: string;
  category: string;
  source_account_code: string;
  beneficiary_name: string;
  beneficiary_member_id?: string;
  cycle_id?: string;
  status: string;
  initiated_by: string;
  initiator_name?: string;
  initiated_at: string;
  approved_by?: string;
  approver_name?: string;
  approved_at?: string;
  rejection_reason?: string;
  executed_by?: string;
  executor_name?: string;
  executed_at?: string;
  payment_reference?: string;
  journal_entry_id?: string;
}

interface MemberOption {
  id: string;
  name: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  committee_payment: 'Committee Payment',
  social_support: 'Social Support',
  admin_cost: 'Administrative Cost',
  end_of_year_payout: 'End-of-Year Payout',
};

const CATEGORY_SOURCE: Record<string, string> = {
  committee_payment: 'ADMIN_FUND',
  social_support: 'SOCIAL_FUND',
  admin_cost: 'ADMIN_FUND',
  end_of_year_payout: 'BANK_CASH',
};

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  executed: 'bg-green-100 text-green-800',
  cancelled: 'bg-gray-100 text-gray-600',
};

function fmtK(n: number) {
  return `K${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function PaymentRequestsPage() {
  const { user } = useAuth();
  const isChairman = user?.roles?.some(r => r.toLowerCase() === 'chairman') ?? false;

  const [requests, setRequests] = useState<PaymentRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [members, setMembers] = useState<MemberOption[]>([]);

  // Create form
  const [showForm, setShowForm] = useState(false);
  const [formAmount, setFormAmount] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formCategory, setFormCategory] = useState('committee_payment');
  const [formBeneficiary, setFormBeneficiary] = useState('');
  const [formMemberId, setFormMemberId] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Account balances
  const [accountBalances, setAccountBalances] = useState<Record<string, number>>({});

  // Active tab
  const [activeTab, setActiveTab] = useState<'requests' | 'reports'>('requests');

  // Reports state
  const [reportMonth, setReportMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [reportSummary, setReportSummary] = useState<{
    total_requests: number;
    total_amount: number;
    executed_amount: number;
    by_status: Record<string, { count: number; total: number }>;
    by_category: Record<string, { count: number; total: number }>;
  } | null>(null);
  const [reportTransactions, setReportTransactions] = useState<PaymentRequest[]>([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportCategoryFilter, setReportCategoryFilter] = useState('all');
  const [reportStatusFilter, setReportStatusFilter] = useState('all');

  // Reject modal
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // Detail modal
  const [selectedRequest, setSelectedRequest] = useState<PaymentRequest | null>(null);

  useEffect(() => {
    loadRequests();
    loadMembers();
    loadAccountBalances();
  }, []);

  const loadRequests = async () => {
    setLoading(true);
    const res = await api.get<PaymentRequest[]>('/api/payment-requests/');
    if (res.data) setRequests(res.data);
    else setError(res.error || 'Failed to load payment requests');
    setLoading(false);
  };

  const loadAccountBalances = async () => {
    const res = await api.get<Record<string, number>>('/api/payment-requests/account-balances');
    if (res.data) setAccountBalances(res.data);
  };

  const loadReports = async () => {
    setReportLoading(true);
    const monthParam = `${reportMonth}-01`;
    const [summaryRes, txnRes] = await Promise.all([
      api.get<typeof reportSummary>(`/api/payment-requests/reports/summary?month=${monthParam}`),
      api.get<{ transactions: PaymentRequest[] }>(`/api/payment-requests/reports/transactions?month=${monthParam}`),
    ]);
    if (summaryRes.data) setReportSummary(summaryRes.data);
    if (txnRes.data) setReportTransactions(txnRes.data.transactions || []);
    setReportLoading(false);
  };

  useEffect(() => {
    if (activeTab === 'reports') loadReports();
  }, [activeTab, reportMonth]);

  const loadMembers = async () => {
    const res = await api.get<{ id: string; user_id: string; first_name: string; last_name: string; status: string }[]>('/api/chairman/members');
    if (res.data) {
      setMembers(res.data.map((m: { id: string; first_name?: string; last_name?: string }) => ({
        id: m.id,
        name: `${(m.first_name || '').trim()} ${(m.last_name || '').trim()}`.trim(),
      })).sort((a: MemberOption, b: MemberOption) => a.name.localeCompare(b.name)));
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    setSuccess('');

    const body: Record<string, unknown> = {
      amount: parseFloat(formAmount),
      description: formDescription,
      category: formCategory,
      beneficiary_name: formBeneficiary,
    };
    if (formCategory === 'end_of_year_payout' && formMemberId) {
      body.beneficiary_member_id = formMemberId;
    }

    const res = await api.post<PaymentRequest>('/api/payment-requests/', body);
    if (res.data) {
      setSuccess('Payment request created successfully');
      setShowForm(false);
      setFormAmount('');
      setFormDescription('');
      setFormCategory('committee_payment');
      setFormBeneficiary('');
      setFormMemberId('');
      loadRequests();
    } else {
      setError(res.error || 'Failed to create payment request');
    }
    setSubmitting(false);
  };

  const handleApprove = async (id: string) => {
    setError('');
    const res = await api.put<PaymentRequest>(`/api/payment-requests/${id}/approve`, {});
    if (res.data) {
      setSuccess('Payment request approved');
      loadRequests();
    } else {
      setError(res.error || 'Failed to approve');
    }
  };

  const handleReject = async () => {
    if (!rejectingId || !rejectReason) return;
    setError('');
    const res = await api.put<PaymentRequest>(`/api/payment-requests/${rejectingId}/reject`, {
      rejection_reason: rejectReason,
    });
    if (res.data) {
      setSuccess('Payment request rejected');
      setRejectingId(null);
      setRejectReason('');
      loadRequests();
    } else {
      setError(res.error || 'Failed to reject');
    }
  };

  const handleCancel = async (id: string) => {
    setError('');
    const res = await api.put<PaymentRequest>(`/api/payment-requests/${id}/cancel`, {});
    if (res.data) {
      setSuccess('Payment request cancelled');
      loadRequests();
    } else {
      setError(res.error || 'Failed to cancel');
    }
  };

  const filtered = statusFilter === 'all' ? requests : requests.filter(r => r.status === statusFilter);

  const counts = {
    all: requests.length,
    pending: requests.filter(r => r.status === 'pending').length,
    approved: requests.filter(r => r.status === 'approved').length,
    executed: requests.filter(r => r.status === 'executed').length,
    rejected: requests.filter(r => r.status === 'rejected').length,
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 font-medium">← Back</Link>
              <h1 className="text-lg font-bold text-blue-900">Payment Requests</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8 pt-20">
        {/* Messages */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border-2 border-red-300 rounded-xl text-red-700 text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 font-bold">×</button>
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-50 border-2 border-green-300 rounded-xl text-green-700 text-sm">
            {success}
            <button onClick={() => setSuccess('')} className="ml-2 font-bold">×</button>
          </div>
        )}

        {/* Tabs */}
        <div className="mb-4 flex gap-1 border-b-2 border-blue-200">
          <button
            onClick={() => setActiveTab('requests')}
            className={`px-4 py-2 text-sm font-semibold rounded-t-lg transition-colors ${activeTab === 'requests' ? 'bg-white text-blue-800 border-2 border-blue-200 border-b-white -mb-[2px]' : 'text-blue-600 hover:bg-blue-50'}`}
          >
            Requests
          </button>
          <button
            onClick={() => setActiveTab('reports')}
            className={`px-4 py-2 text-sm font-semibold rounded-t-lg transition-colors ${activeTab === 'reports' ? 'bg-white text-blue-800 border-2 border-blue-200 border-b-white -mb-[2px]' : 'text-blue-600 hover:bg-blue-50'}`}
          >
            Reports
          </button>
        </div>

        {activeTab === 'requests' && (<>
        {/* Create button */}
        <div className="mb-4 flex items-center justify-between">
          <div className="flex gap-2 flex-wrap">
            {(['all', 'pending', 'approved', 'executed', 'rejected'] as const).map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${statusFilter === s ? 'bg-blue-600 text-white' : 'bg-white text-blue-700 border border-blue-300 hover:bg-blue-50'}`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)} ({counts[s]})
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 transition-colors"
          >
            {showForm ? 'Cancel' : '+ New Request'}
          </button>
        </div>

        {/* Create form */}
        {showForm && (
          <div className="mb-6 card">
            <h2 className="text-lg font-bold text-blue-900 mb-4">Create Payment Request</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-blue-900 mb-1">Category *</label>
                  <select
                    value={formCategory}
                    onChange={e => {
                      setFormCategory(e.target.value);
                      if (e.target.value === 'end_of_year_payout') setFormBeneficiary('');
                    }}
                    className="w-full"
                    required
                  >
                    <option value="committee_payment">Committee Payment — Admin Fund ({fmtK(accountBalances['ADMIN_FUND'] || 0)})</option>
                    <option value="social_support">Social Support — Social Fund ({fmtK(accountBalances['SOCIAL_FUND'] || 0)})</option>
                    <option value="admin_cost">Administrative Cost — Admin Fund ({fmtK(accountBalances['ADMIN_FUND'] || 0)})</option>
                    <option value="end_of_year_payout">End-of-Year Payout — Bank Cash ({fmtK(accountBalances['BANK_CASH'] || 0)})</option>
                  </select>
                  <p className="mt-1 text-xs text-blue-600">
                    Available in {CATEGORY_SOURCE[formCategory].replace(/_/g, ' ')}: <span className="font-semibold">{fmtK(accountBalances[CATEGORY_SOURCE[formCategory]] || 0)}</span>
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-blue-900 mb-1">Amount (K) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={formAmount}
                    onChange={e => setFormAmount(e.target.value)}
                    className="w-full"
                    placeholder="0.00"
                    required
                  />
                </div>

                {formCategory === 'end_of_year_payout' ? (
                  <div>
                    <label className="block text-sm font-semibold text-blue-900 mb-1">Beneficiary Member *</label>
                    <select
                      value={formMemberId}
                      onChange={e => {
                        setFormMemberId(e.target.value);
                        const m = members.find(m => m.id === e.target.value);
                        if (m) setFormBeneficiary(m.name);
                      }}
                      className="w-full"
                      required
                    >
                      <option value="">Select member...</option>
                      {members.map(m => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-semibold text-blue-900 mb-1">Beneficiary Name *</label>
                    <input
                      type="text"
                      value={formBeneficiary}
                      onChange={e => setFormBeneficiary(e.target.value)}
                      className="w-full"
                      placeholder="Person or entity receiving payment"
                      required
                    />
                  </div>
                )}

                <div className="md:col-span-2">
                  <label className="block text-sm font-semibold text-blue-900 mb-1">Description *</label>
                  <textarea
                    value={formDescription}
                    onChange={e => setFormDescription(e.target.value)}
                    className="w-full"
                    rows={2}
                    placeholder="Reason for payment..."
                    required
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {submitting ? 'Creating...' : 'Submit Request'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Request list */}
        {loading ? (
          <div className="text-center py-16">
            <div className="animate-spin rounded-full h-14 w-14 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <p className="mt-4 text-blue-700">Loading...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="card text-center py-12 text-blue-600">
            No payment requests found.
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(pr => (
              <div key={pr.id} className="card hover:shadow-lg transition-shadow">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                  {/* Left: info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[pr.status]}`}>
                        {pr.status.charAt(0).toUpperCase() + pr.status.slice(1)}
                      </span>
                      <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
                        {CATEGORY_LABELS[pr.category] || pr.category}
                      </span>
                      <span className="text-lg font-bold text-blue-900">{fmtK(pr.amount)}</span>
                    </div>
                    <p className="text-sm text-blue-800 font-medium">{pr.description}</p>
                    <p className="text-xs text-blue-600 mt-1">
                      To: <span className="font-semibold">{pr.beneficiary_name}</span>
                      {' · '}From: {pr.source_account_code.replace('_', ' ')}
                    </p>
                    <p className="text-xs text-blue-500 mt-0.5">
                      Created by {pr.initiator_name || 'Unknown'} on {fmtDate(pr.initiated_at)}
                    </p>
                    {pr.approved_at && (
                      <p className="text-xs text-blue-500">
                        {pr.status === 'rejected' ? 'Rejected' : 'Approved'} by {pr.approver_name || 'Unknown'} on {fmtDate(pr.approved_at)}
                      </p>
                    )}
                    {pr.rejection_reason && (
                      <p className="text-xs text-red-600 mt-1">Reason: {pr.rejection_reason}</p>
                    )}
                    {pr.executed_at && (
                      <p className="text-xs text-green-700">
                        Executed by {pr.executor_name || 'Unknown'} on {fmtDate(pr.executed_at)}
                        {pr.payment_reference && ` · Ref: ${pr.payment_reference}`}
                      </p>
                    )}
                  </div>

                  {/* Right: actions */}
                  <div className="flex gap-2 shrink-0">
                    {pr.status === 'pending' && isChairman && (
                      <>
                        <button
                          onClick={() => handleApprove(pr.id)}
                          className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => { setRejectingId(pr.id); setRejectReason(''); }}
                          className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs font-semibold hover:bg-red-600"
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {pr.status === 'pending' && pr.initiated_by === user?.id && (
                      <button
                        onClick={() => handleCancel(pr.id)}
                        className="px-3 py-1.5 bg-gray-400 text-white rounded-lg text-xs font-semibold hover:bg-gray-500"
                      >
                        Cancel
                      </button>
                    )}
                    {pr.status === 'approved' && (
                      <span className="text-xs text-blue-600 italic">Awaiting Treasurer</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Reject modal */}
        {/* Reject modal */}
        {rejectingId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
              <h3 className="text-lg font-bold text-red-800 mb-3">Reject Payment Request</h3>
              <textarea
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                className="w-full mb-4"
                rows={3}
                placeholder="Reason for rejection..."
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => setRejectingId(null)} className="px-4 py-2 bg-gray-200 rounded-lg text-sm font-semibold">
                  Cancel
                </button>
                <button
                  onClick={handleReject}
                  disabled={!rejectReason.trim()}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}
        </>)}

        {/* ── Reports Tab ─────────────────────────────────────────────── */}
        {activeTab === 'reports' && (
          <div className="space-y-4">
            {/* Controls */}
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="month"
                value={reportMonth}
                onChange={e => setReportMonth(e.target.value)}
                className="px-3 py-1.5 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <select
                value={reportCategoryFilter}
                onChange={e => setReportCategoryFilter(e.target.value)}
                className="px-3 py-1.5 border-2 border-blue-300 rounded-lg text-sm"
              >
                <option value="all">All Categories</option>
                <option value="committee_payment">Committee Payment</option>
                <option value="social_support">Social Support</option>
                <option value="admin_cost">Administrative Cost</option>
                <option value="end_of_year_payout">End-of-Year Payout</option>
              </select>
              <select
                value={reportStatusFilter}
                onChange={e => setReportStatusFilter(e.target.value)}
                className="px-3 py-1.5 border-2 border-blue-300 rounded-lg text-sm"
              >
                <option value="all">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="executed">Executed</option>
                <option value="rejected">Rejected</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <button
                onClick={() => window.print()}
                className="ml-auto px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 print:hidden"
              >
                Print
              </button>
            </div>

            {reportLoading ? (
              <div className="text-center py-16">
                <div className="animate-spin rounded-full h-14 w-14 border-4 border-blue-200 border-t-blue-600 mx-auto" />
                <p className="mt-4 text-blue-700">Loading report...</p>
              </div>
            ) : (
              <>
                {/* Summary cards */}
                {reportSummary && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="card text-center">
                      <p className="text-xs text-blue-600 font-semibold">Total Requests</p>
                      <p className="text-2xl font-bold text-blue-900">{reportSummary.total_requests}</p>
                    </div>
                    <div className="card text-center">
                      <p className="text-xs text-blue-600 font-semibold">Total Amount</p>
                      <p className="text-2xl font-bold text-blue-900">{fmtK(reportSummary.total_amount)}</p>
                    </div>
                    <div className="card text-center">
                      <p className="text-xs text-green-600 font-semibold">Executed</p>
                      <p className="text-2xl font-bold text-green-700">{fmtK(reportSummary.executed_amount)}</p>
                    </div>
                    <div className="card text-center">
                      <p className="text-xs text-orange-600 font-semibold">Pending</p>
                      <p className="text-2xl font-bold text-orange-700">
                        {fmtK(reportSummary.by_status?.pending?.total || 0)}
                      </p>
                    </div>
                  </div>
                )}

                {/* Breakdown by category */}
                {reportSummary && Object.keys(reportSummary.by_category).length > 0 && (
                  <div className="card">
                    <h3 className="text-base font-bold text-blue-900 mb-3">By Category</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b-2 border-blue-200 text-left text-blue-700">
                            <th className="py-2 px-3">Category</th>
                            <th className="py-2 px-3 text-right">Count</th>
                            <th className="py-2 px-3 text-right">Total Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(reportSummary.by_category).map(([cat, data]) => (
                            <tr key={cat} className="border-b border-blue-100">
                              <td className="py-2 px-3 font-medium">{CATEGORY_LABELS[cat] || cat}</td>
                              <td className="py-2 px-3 text-right">{data.count}</td>
                              <td className="py-2 px-3 text-right font-semibold">{fmtK(data.total)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Breakdown by status */}
                {reportSummary && Object.keys(reportSummary.by_status).length > 0 && (
                  <div className="card">
                    <h3 className="text-base font-bold text-blue-900 mb-3">By Status</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b-2 border-blue-200 text-left text-blue-700">
                            <th className="py-2 px-3">Status</th>
                            <th className="py-2 px-3 text-right">Count</th>
                            <th className="py-2 px-3 text-right">Total Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(reportSummary.by_status).map(([st, data]) => (
                            <tr key={st} className="border-b border-blue-100">
                              <td className="py-2 px-3">
                                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[st] || 'bg-gray-100'}`}>
                                  {st.charAt(0).toUpperCase() + st.slice(1)}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">{data.count}</td>
                              <td className="py-2 px-3 text-right font-semibold">{fmtK(data.total)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Transaction list */}
                <div className="card">
                  <h3 className="text-base font-bold text-blue-900 mb-3">
                    Transactions ({(() => {
                      let txns = reportTransactions;
                      if (reportCategoryFilter !== 'all') txns = txns.filter(t => t.category === reportCategoryFilter);
                      if (reportStatusFilter !== 'all') txns = txns.filter(t => t.status === reportStatusFilter);
                      return txns.length;
                    })()})
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs whitespace-nowrap">
                      <thead>
                        <tr className="border-b-2 border-blue-200 text-left text-blue-700">
                          <th className="py-2 px-2">#</th>
                          <th className="py-2 px-2">Date</th>
                          <th className="py-2 px-2">Category</th>
                          <th className="py-2 px-2">Description</th>
                          <th className="py-2 px-2">Beneficiary</th>
                          <th className="py-2 px-2 text-right">Amount</th>
                          <th className="py-2 px-2">Status</th>
                          <th className="py-2 px-2">Initiated By</th>
                          <th className="py-2 px-2">Approved By</th>
                          <th className="py-2 px-2">Executed By</th>
                          <th className="py-2 px-2">Reference</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(() => {
                          let txns = reportTransactions;
                          if (reportCategoryFilter !== 'all') txns = txns.filter(t => t.category === reportCategoryFilter);
                          if (reportStatusFilter !== 'all') txns = txns.filter(t => t.status === reportStatusFilter);
                          if (txns.length === 0) return (
                            <tr><td colSpan={11} className="py-8 text-center text-blue-500">No transactions found for this period.</td></tr>
                          );
                          return txns.map((t, i) => (
                            <tr key={t.id} className={`border-b border-blue-50 ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}`}>
                              <td className="py-1.5 px-2 text-blue-500">{i + 1}</td>
                              <td className="py-1.5 px-2">{new Date(t.initiated_at).toLocaleDateString('en-US', { day: 'numeric', month: 'short' })}</td>
                              <td className="py-1.5 px-2">{CATEGORY_LABELS[t.category] || t.category}</td>
                              <td className="py-1.5 px-2 max-w-[200px] truncate" title={t.description}>{t.description}</td>
                              <td className="py-1.5 px-2">{t.beneficiary_name}</td>
                              <td className="py-1.5 px-2 text-right font-semibold">{fmtK(t.amount)}</td>
                              <td className="py-1.5 px-2">
                                <span className={`px-1.5 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[t.status]}`}>
                                  {t.status.charAt(0).toUpperCase() + t.status.slice(1)}
                                </span>
                              </td>
                              <td className="py-1.5 px-2">{t.initiator_name || '-'}</td>
                              <td className="py-1.5 px-2">{t.approver_name || '-'}</td>
                              <td className="py-1.5 px-2">{t.executor_name || '-'}</td>
                              <td className="py-1.5 px-2">{t.payment_reference || '-'}</td>
                            </tr>
                          ));
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
