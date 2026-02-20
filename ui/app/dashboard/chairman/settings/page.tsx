'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import UserMenu from '@/components/UserMenu';

interface LoanTerm {
  term_months: string;
  sort_order: number;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const [loanTerms, setLoanTerms] = useState<LoanTerm[]>([]);
  const [newTerm, setNewTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetchTerms();
  }, []);

  const fetchTerms = async () => {
    setLoading(true);
    const res = await api.get<LoanTerm[]>('/api/chairman/settings/loan-terms');
    if (res.data) setLoanTerms(res.data);
    setLoading(false);
  };

  const handleAdd = async () => {
    setMessage(null);
    const parsed = parseInt(newTerm, 10);
    if (!newTerm || isNaN(parsed) || parsed <= 0) {
      setMessage({ type: 'error', text: 'Please enter a valid positive number.' });
      return;
    }
    const res = await api.post<LoanTerm[]>('/api/chairman/settings/loan-terms', { term_months: String(parsed) });
    if (res.data) {
      setLoanTerms(res.data);
      setNewTerm('');
      setMessage({ type: 'success', text: `${parsed}-month term added.` });
    } else {
      setMessage({ type: 'error', text: res.error || 'Failed to add term.' });
    }
  };

  const handleDelete = async (term: string) => {
    setMessage(null);
    const res = await api.delete<LoanTerm[]>(`/api/chairman/settings/loan-terms/${term}`);
    if (res.data) {
      setLoanTerms(res.data);
      setMessage({ type: 'success', text: `${term}-month term removed.` });
    } else {
      setMessage({ type: 'error', text: res.error || 'Failed to delete term.' });
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back to Dashboard
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Settings</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="card">
          <h2 className="text-xl font-bold text-blue-900 mb-2">Loan Term Options</h2>
          <p className="text-sm text-blue-700 mb-6">
            Configure which loan term lengths (in months) are available across the system — cycle interest rate ranges, reconciliation, and member loan applications.
          </p>

          {message && (
            <div className={`mb-4 px-4 py-3 rounded-lg text-sm font-medium ${message.type === 'success' ? 'bg-green-100 text-green-800 border border-green-300' : 'bg-red-100 text-red-800 border border-red-300'}`}>
              {message.text}
            </div>
          )}

          {loading ? (
            <p className="text-blue-600 text-sm">Loading…</p>
          ) : (
            <>
              <ul className="space-y-2 mb-6">
                {loanTerms.map((t) => (
                  <li key={t.term_months} className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
                    <span className="font-semibold text-blue-900">
                      {t.term_months} {t.term_months === '1' ? 'Month' : 'Months'}
                    </span>
                    <button
                      onClick={() => handleDelete(t.term_months)}
                      className="text-red-600 hover:text-red-800 text-sm font-medium px-3 py-1 border border-red-300 rounded-lg hover:bg-red-50 transition-colors"
                    >
                      Delete
                    </button>
                  </li>
                ))}
                {loanTerms.length === 0 && (
                  <li className="text-blue-500 text-sm italic">No loan terms configured.</li>
                )}
              </ul>

              <div className="flex gap-3 items-center">
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  placeholder="e.g. 5"
                  className="w-32 px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                />
                <span className="text-sm text-blue-700">months</span>
                <button
                  onClick={handleAdd}
                  className="px-5 py-2 bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-lg font-semibold text-sm hover:from-blue-600 hover:to-blue-700 border-2 border-blue-600 transition-all"
                >
                  Add Term
                </button>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
