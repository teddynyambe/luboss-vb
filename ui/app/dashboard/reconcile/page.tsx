'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import UserMenu from '@/components/UserMenu';

interface Member {
  id: string;
  user?: { first_name?: string; last_name?: string; email?: string };
}

interface FormData {
  savings_amount: string;
  social_fund: string;
  admin_fund: string;
  penalties: string;
  interest_on_loan: string;
  loan_repayment: string;
  loan_amount: string;
  loan_rate: string;
  loan_term_months: string;
}

const emptyForm: FormData = {
  savings_amount: '0',
  social_fund: '0',
  admin_fund: '0',
  penalties: '0',
  interest_on_loan: '0',
  loan_repayment: '0',
  loan_amount: '0',
  loan_rate: '0',
  loan_term_months: '1',
};

export default function ReconcilePage() {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState('');
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [formData, setFormData] = useState<FormData>(emptyForm);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loanTermOptions, setLoanTermOptions] = useState<string[]>([]);

  useEffect(() => {
    api.get<Member[]>('/api/chairman/members?status=active').then((res) => {
      if (res.data) setMembers(res.data);
    });
    api.get<{ term_months: string }[]>('/api/chairman/settings/loan-terms').then((res) => {
      if (res.data) setLoanTermOptions(res.data.map((t) => t.term_months));
    });
  }, []);

  // Reset form when member or month changes after a load
  const handleMemberChange = (id: string) => {
    setSelectedMemberId(id);
    setLoaded(false);
    setFormData(emptyForm);
    setMessage(null);
  };

  const handleMonthChange = (m: string) => {
    setSelectedMonth(m);
    setLoaded(false);
    setFormData(emptyForm);
    setMessage(null);
  };

  const handleLoad = async () => {
    if (!selectedMemberId || !selectedMonth) {
      setMessage({ type: 'error', text: 'Please select a member and month.' });
      return;
    }
    const now = new Date();
    const maxMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    if (selectedMonth > maxMonth) {
      setMessage({ type: 'error', text: 'Cannot reconcile a future month.' });
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const monthDate = `${selectedMonth}-01`;
      const res = await api.get<{
        declaration: {
          savings_amount: number;
          social_fund: number;
          admin_fund: number;
          penalties: number;
          interest_on_loan: number;
          loan_repayment: number;
          status: string | null;
        };
        loan: { loan_amount: number; loan_rate: number; loan_term_months: string };
      }>(`/api/chairman/reconcile?member_id=${selectedMemberId}&month=${monthDate}`);

      if (res.data) {
        const d = res.data.declaration;
        const l = res.data.loan;
        setFormData({
          savings_amount: String(d.savings_amount ?? 0),
          social_fund: String(d.social_fund ?? 0),
          admin_fund: String(d.admin_fund ?? 0),
          penalties: String(d.penalties ?? 0),
          interest_on_loan: String(d.interest_on_loan ?? 0),
          loan_repayment: String(d.loan_repayment ?? 0),
          loan_amount: String(l.loan_amount ?? 0),
          loan_rate: String(l.loan_rate ?? 0),
          loan_term_months: l.loan_term_months || '1',
        });
        setLoaded(true);
      } else {
        setMessage({ type: 'error', text: res.error || 'Failed to load data' });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    const now = new Date();
    const maxMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    if (selectedMonth > maxMonth) {
      setMessage({ type: 'error', text: 'Cannot reconcile a future month.' });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const monthDate = `${selectedMonth}-01`;
      const res = await api.post('/api/chairman/reconcile', {
        member_id: selectedMemberId,
        month: monthDate,
        savings_amount: parseFloat(formData.savings_amount) || 0,
        social_fund: parseFloat(formData.social_fund) || 0,
        admin_fund: parseFloat(formData.admin_fund) || 0,
        penalties: parseFloat(formData.penalties) || 0,
        interest_on_loan: parseFloat(formData.interest_on_loan) || 0,
        loan_repayment: parseFloat(formData.loan_repayment) || 0,
        loan_amount: parseFloat(formData.loan_amount) || 0,
        loan_rate: parseFloat(formData.loan_rate) || 0,
        loan_term_months: formData.loan_term_months || '1',
      });

      if (!res.error) {
        setMessage({ type: 'success', text: 'Reconciliation saved successfully!' });
      } else {
        setMessage({ type: 'error', text: res.error || 'Failed to save reconciliation' });
      }
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(null), 6000);
    }
  };

  const field = (label: string, key: keyof FormData) => (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-semibold text-blue-900">{label}</label>
      <input
        type="number"
        min="0"
        step="0.01"
        value={formData[key]}
        onChange={(e) => setFormData((prev) => ({ ...prev, [key]: e.target.value }))}
        className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  );

  const getMemberName = (m: Member) => {
    const fn = m.user?.first_name || '';
    const ln = m.user?.last_name || '';
    const name = `${fn} ${ln}`.trim();
    return name || m.user?.email || m.id;
  };

  const selectedMember = members.find((m) => m.id === selectedMemberId);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Dashboard
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Reconciliation</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-6">
        {message && (
          <div
            className={`px-4 py-3 rounded-xl text-base font-medium ${
              message.type === 'success'
                ? 'bg-green-100 border-2 border-green-400 text-green-800'
                : 'bg-red-100 border-2 border-red-400 text-red-800'
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Member + Month selector */}
        <div className="card">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
              <label className="text-sm font-semibold text-blue-900">Member</label>
              <select
                value={selectedMemberId}
                onChange={(e) => handleMemberChange(e.target.value)}
                className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select member…</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {getMemberName(m)}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-semibold text-blue-900">Month</label>
              <input
                type="month"
                value={selectedMonth}
                max={`${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`}
                onChange={(e) => handleMonthChange(e.target.value)}
                className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              onClick={handleLoad}
              disabled={loading || !selectedMemberId}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? 'Loading…' : 'Load'}
            </button>
          </div>
        </div>

        {/* Form — only visible after Load succeeds */}
        {loaded && (
          <>
            {/* Context banner */}
            <div className="px-4 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium">
              {selectedMember ? getMemberName(selectedMember) : selectedMemberId}
              {' — '}
              {(() => {
                const [y, m] = selectedMonth.split('-').map(Number);
                return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
              })()}
            </div>

            {/* Declaration fields */}
            <div className="card">
              <h2 className="text-lg font-bold text-blue-900 mb-4">Declaration</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {field('Savings Declared (K)', 'savings_amount')}
                {field('Social Fund (K)', 'social_fund')}
                {field('Admin Fund (K)', 'admin_fund')}
                {field('Penalties (K)', 'penalties')}
                {field('Loan Repayment (K)', 'loan_repayment')}
                {field('Interest on Loan (K)', 'interest_on_loan')}
              </div>
            </div>

            {/* Loan fields */}
            <div className="card">
              <h2 className="text-lg font-bold text-blue-900 mb-4">Loan Applied (leave 0 if none)</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {field('Loan Amount (K)', 'loan_amount')}
                {field('Interest Rate (%)', 'loan_rate')}
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-semibold text-blue-900">Loan Term (Months)</label>
                  <select
                    value={formData.loan_term_months}
                    onChange={(e) => setFormData((prev) => ({ ...prev, loan_term_months: e.target.value }))}
                    className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {loanTermOptions.length > 0 ? (
                      loanTermOptions.map((t) => (
                        <option key={t} value={t}>
                          {t} {t === '1' ? 'Month' : 'Months'}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="1">1 Month</option>
                        <option value="2">2 Months</option>
                        <option value="3">3 Months</option>
                        <option value="4">4 Months</option>
                      </>
                    )}
                  </select>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-8 py-3 bg-gradient-to-br from-green-500 to-green-600 border-2 border-green-600 text-white rounded-xl font-bold text-base hover:from-green-600 hover:to-green-700 disabled:opacity-50 transition-all"
              >
                {saving ? 'Saving…' : 'Save Reconciliation'}
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
