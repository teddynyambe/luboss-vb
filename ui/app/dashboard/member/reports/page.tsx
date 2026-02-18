'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface MemberRow {
  name: string;
  savings_bf: number;
  social_admin_bf: number;
  interest_bf: number;
  loan_bf: number;
  savings_declared: number;
  social_admin_declared: number;
  penalty: number;
  loan_repayment: number;
  interest_on_loan_paid: number;
  total_deposited: number;
  interest_earned: number;
  loan_applied: number;
  interest_on_loan_applied: number;
}

interface GroupSummary {
  month: string;
  members: MemberRow[];
  totals: MemberRow;
}

const COLS: { key: keyof MemberRow; label: string; title: string }[] = [
  { key: 'savings_bf',             label: 'Savings B/F',       title: 'Savings brought forward from previous month' },
  { key: 'social_admin_bf',        label: 'Social & Admin B/F',title: 'Social & Admin fund accumulated to date' },
  { key: 'interest_bf',            label: 'Interest B/F',      title: 'Proportional interest earned in previous months' },
  { key: 'loan_bf',                label: 'Loan B/F',          title: 'Outstanding loan balance at month start' },
  { key: 'savings_declared',       label: 'Savings Declared',  title: 'Savings amount declared this month' },
  { key: 'social_admin_declared',  label: 'Social & Admin',    title: 'Social & Admin contribution declared this month' },
  { key: 'penalty',                label: 'Penalty',           title: 'Approved penalties this month' },
  { key: 'loan_repayment',         label: 'Loan Repayment',    title: 'Principal repaid this month' },
  { key: 'interest_on_loan_paid',  label: 'Interest Paid',     title: 'Loan interest paid this month' },
  { key: 'total_deposited',        label: 'Total Deposited',   title: 'Approved deposit amount this month' },
  { key: 'interest_earned',        label: 'Interest Earned',   title: 'Proportional profit share this month (based on savings B/F)' },
  { key: 'loan_applied',           label: 'Loan Applied',      title: 'New loans disbursed this month' },
  { key: 'interest_on_loan_applied', label: 'Interest on Loan', title: 'Monthly interest on newly applied loan' },
];

function fmt(n: number): string {
  if (n === 0) return '';
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTotal(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function GroupReportPage() {
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  );
  const [summary, setSummary] = useState<GroupSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadReport();
  }, [selectedMonth]);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    const monthDate = `${selectedMonth}-01`;
    const res = await api.get<GroupSummary>(`/api/member/reports/group-summary?month=${monthDate}`);
    if (res.data) {
      setSummary(res.data);
    } else {
      setError(res.error || 'Failed to load report');
    }
    setLoading(false);
  };

  const formatMonthLabel = (m: string) => {
    const [y, mo] = m.split('-').map(Number);
    return new Date(y, mo - 1, 1).toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  };

  // Determine which columns have any non-zero value (skip all-zero columns)
  const activeCols = summary
    ? COLS.filter(c =>
        c.key === 'savings_bf' ||          // always show savings B/F
        c.key === 'total_deposited' ||      // always show total deposited
        summary.members.some(r => (r[c.key] as number) !== 0)
      )
    : COLS;

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-3">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 font-medium">
                ← Back
              </Link>
              <h1 className="text-lg font-bold text-blue-900">Group Report</h1>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="month"
                value={selectedMonth}
                onChange={e => setSelectedMonth(e.target.value)}
                className="px-3 py-1.5 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <UserMenu />
            </div>
          </div>
        </div>
      </nav>

      <main className="py-4 px-2 sm:px-4 pt-20">
        {loading ? (
          <div className="text-center py-16">
            <div className="animate-spin rounded-full h-14 w-14 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <p className="mt-4 text-blue-700">Loading report...</p>
          </div>
        ) : error ? (
          <div className="max-w-lg mx-auto mt-8 p-4 bg-red-50 border-2 border-red-300 rounded-xl text-red-700">
            {error}
          </div>
        ) : summary ? (
          <div>
            <div className="mb-3 flex items-center justify-between px-1">
              <h2 className="text-base font-bold text-blue-900">
                {formatMonthLabel(selectedMonth)} — {summary.members.length} members
              </h2>
              <button
                onClick={() => window.print()}
                className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition-colors print:hidden"
              >
                Print
              </button>
            </div>

            <div ref={tableRef} className="overflow-x-auto rounded-xl shadow-lg bg-white">
              <table className="text-xs whitespace-nowrap border-collapse w-full">
                <thead>
                  {/* Group headers */}
                  <tr className="bg-blue-700 text-white">
                    <th className="sticky left-0 z-10 bg-blue-700 px-3 py-2 text-left font-bold border-r border-blue-500" rowSpan={2}>
                      #
                    </th>
                    <th className="sticky left-7 z-10 bg-blue-700 px-3 py-2 text-left font-bold border-r border-blue-500 min-w-[140px]" rowSpan={2}>
                      Name
                    </th>
                    <th className="px-2 py-1.5 text-center font-semibold border-r border-blue-500" colSpan={4}>
                      Brought Forward
                    </th>
                    <th className="px-2 py-1.5 text-center font-semibold border-r border-blue-500" colSpan={5}>
                      This Month
                    </th>
                    <th className="px-2 py-1.5 text-center font-semibold" colSpan={4}>
                      Month End
                    </th>
                  </tr>
                  <tr className="bg-blue-600 text-white">
                    {activeCols.map(c => (
                      <th key={c.key} title={c.title}
                        className="px-3 py-1.5 text-right font-semibold border-l border-blue-500 min-w-[90px]">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summary.members.map((row, i) => {
                    const paid = row.total_deposited > 0 && row.savings_declared > 0
                      && row.total_deposited >= row.savings_declared;
                    return (
                      <tr key={row.name}
                        className={`border-b border-blue-100 hover:bg-blue-50 transition-colors
                          ${paid ? 'bg-green-50' : i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}`}>
                        <td className="sticky left-0 z-10 bg-inherit px-2 py-1.5 text-blue-500 border-r border-blue-100 text-right w-7">
                          {i + 1}
                        </td>
                        <td className="sticky left-7 z-10 bg-inherit px-3 py-1.5 font-medium text-blue-900 border-r border-blue-100">
                          {row.name}
                        </td>
                        {activeCols.map(c => (
                          <td key={c.key} className="px-3 py-1.5 text-right text-blue-800 border-l border-blue-50">
                            {fmt(row[c.key] as number)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-blue-800 text-white font-bold border-t-2 border-blue-400">
                    <td className="sticky left-0 z-10 bg-blue-800 px-2 py-2 border-r border-blue-600" />
                    <td className="sticky left-7 z-10 bg-blue-800 px-3 py-2 border-r border-blue-600">
                      TOTAL
                    </td>
                    {activeCols.map(c => (
                      <td key={c.key} className="px-3 py-2 text-right border-l border-blue-600">
                        {fmtTotal(summary.totals[c.key] as number)}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>

            <p className="mt-3 text-xs text-blue-600 px-1 print:hidden">
              Green rows = member has deposited ≥ declared savings this month.
              Interest earned is distributed proportionally based on each member's savings brought forward.
            </p>
          </div>
        ) : null}
      </main>
    </div>
  );
}
