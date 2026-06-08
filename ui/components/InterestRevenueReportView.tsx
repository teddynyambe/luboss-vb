'use client';

import { Fragment, useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import UserMenu from '@/components/UserMenu';

interface LoanRow {
  loan_id: string;
  member_id: string;
  member_name: string;
  loan_amount: number;
  term_months: string | null;
  rate_pct: number;
  interest_accrued: number;
  interest_collected: number;
  outstanding: number;
  loan_status: string | null;
  aging_days: number;
  aging_bucket: 'current' | '31_60' | '61_90' | 'over_90';
}

interface MonthRow {
  month: string;
  month_label: string;
  loans_disbursed_count: number;
  loans_disbursed_amount: number;
  interest_accrued: number;
  interest_collected: number;
  outstanding_from_this_month: number;
  collection_pct: number | null;
  loans: LoanRow[];
}

interface ReportPayload {
  cycle_id: string | null;
  cycle_label: string | null;
  today: string;
  months: MonthRow[];
  totals: {
    loans_disbursed_count: number;
    loans_disbursed_amount: number;
    interest_accrued: number;
    interest_collected: number;
    outstanding: number;
    collection_pct: number | null;
  };
  top_outstanding_borrowers: { member_id: string; member_name: string; outstanding: number }[];
}

const fmtK = (n: number) =>
  `K${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtPct = (n: number | null) => (n === null ? '—' : `${n.toFixed(1)}%`);

const agingLabel = (b: LoanRow['aging_bucket']) =>
  ({ current: 'Current', '31_60': '31–60 d', '61_90': '61–90 d', over_90: '> 90 d' })[b];

const agingClass = (b: LoanRow['aging_bucket']) =>
  ({
    current: 'bg-emerald-100 text-emerald-800',
    '31_60': 'bg-yellow-100 text-yellow-800',
    '61_90': 'bg-orange-100 text-orange-800',
    over_90: 'bg-red-100 text-red-800',
  })[b];

interface Props {
  /** API endpoint to fetch the report payload from. Both treasurer and member
   * endpoints return the same shape — they just differ in role-guard. */
  endpoint: string;
  /** Where the Back link returns to. */
  backHref: string;
}

export default function InterestRevenueReportView({ endpoint, backHref }: Props) {
  const [data, setData] = useState<ReportPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedMonth, setExpandedMonth] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .get<ReportPayload>(endpoint)
      .then((res) => {
        if (res.data) setData(res.data);
        else setError(res.error || 'Failed to load report');
      })
      .finally(() => setLoading(false));
  }, [endpoint]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center gap-3">
              <Link href={backHref} className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Loan/Revenue Report</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-4">
        {loading && (
          <div className="card text-center py-10">
            <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <p className="mt-3 text-blue-700">Loading…</p>
          </div>
        )}

        {error && <div className="card text-red-700">{error}</div>}

        {data && !loading && (
          <>
            {/* Headline metric cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Metric label="Loans Disbursed" value={`${data.totals.loans_disbursed_count}`} sub={fmtK(data.totals.loans_disbursed_amount)} tone="blue" />
              <Metric label="Interest Accrued" value={fmtK(data.totals.interest_accrued)} sub="Recognised as income" tone="emerald" />
              <Metric label="Interest Collected" value={fmtK(data.totals.interest_collected)} sub="Cash received" tone="blue" />
              <Metric label="Outstanding" value={fmtK(data.totals.outstanding)} sub="Receivable" tone="amber" />
              <Metric label="Collection %" value={fmtPct(data.totals.collection_pct)} sub="Collected ÷ Accrued" tone="indigo" />
            </div>

            {/* Top borrowers */}
            {data.top_outstanding_borrowers.length > 0 && (
              <div className="card">
                <h3 className="text-sm font-bold text-blue-900 mb-2">Top 5 borrowers by outstanding receivable</h3>
                <ol className="text-sm space-y-1">
                  {data.top_outstanding_borrowers.map((b, i) => (
                    <li key={b.member_id} className="flex justify-between border-b border-blue-100 last:border-0 py-1">
                      <span className="text-blue-800">{i + 1}. {b.member_name}</span>
                      <span className="font-semibold text-amber-700">{fmtK(b.outstanding)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* Monthly breakdown */}
            <div className="card">
              <h3 className="text-sm font-bold text-blue-900 mb-3">Monthly breakdown — click a month to drill into per-loan detail</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b-2 border-blue-200 text-blue-700">
                      <th className="text-left py-2 pr-3">Month</th>
                      <th className="text-right py-2 pr-3">Loans</th>
                      <th className="text-right py-2 pr-3">Disbursed</th>
                      <th className="text-right py-2 pr-3">Interest Accrued</th>
                      <th className="text-right py-2 pr-3">Interest Collected</th>
                      <th className="text-right py-2 pr-3">Outstanding</th>
                      <th className="text-right py-2">Collection %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-blue-100">
                    {data.months.length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-blue-600 italic">No loans on file.</td></tr>
                    )}
                    {data.months.map((m) => (
                      <Fragment key={m.month}>
                        <tr
                          className="hover:bg-blue-50 cursor-pointer"
                          onClick={() => setExpandedMonth(expandedMonth === m.month ? null : m.month)}
                        >
                          <td className="py-2 pr-3 text-blue-900 font-semibold">
                            <span className="inline-block w-4">{expandedMonth === m.month ? '▾' : '▸'}</span>
                            {m.month_label}
                          </td>
                          <td className="py-2 pr-3 text-right text-blue-800">{m.loans_disbursed_count}</td>
                          <td className="py-2 pr-3 text-right text-blue-800">{fmtK(m.loans_disbursed_amount)}</td>
                          <td className="py-2 pr-3 text-right text-emerald-700 font-semibold">{fmtK(m.interest_accrued)}</td>
                          <td className="py-2 pr-3 text-right text-blue-800">{fmtK(m.interest_collected)}</td>
                          <td className="py-2 pr-3 text-right text-amber-700 font-semibold">{fmtK(m.outstanding_from_this_month)}</td>
                          <td className="py-2 text-right text-indigo-700">{fmtPct(m.collection_pct)}</td>
                        </tr>
                        {expandedMonth === m.month && (
                          <tr>
                            <td colSpan={7} className="py-2 px-2 bg-blue-50/60">
                              <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="text-blue-700">
                                      <th className="text-left py-1 pr-2">Member</th>
                                      <th className="text-left py-1 pr-2">Loan</th>
                                      <th className="text-right py-1 pr-2">Amount</th>
                                      <th className="text-left py-1 pr-2">Term</th>
                                      <th className="text-right py-1 pr-2">Rate</th>
                                      <th className="text-right py-1 pr-2">Accrued</th>
                                      <th className="text-right py-1 pr-2">Paid</th>
                                      <th className="text-right py-1 pr-2">Outstanding</th>
                                      <th className="text-center py-1">Aging</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-blue-100">
                                    {m.loans.map((l) => (
                                      <tr key={l.loan_id}>
                                        <td className="py-1 pr-2 text-blue-900">{l.member_name}</td>
                                        <td className="py-1 pr-2 font-mono text-blue-600">{l.loan_id.slice(0, 8)}</td>
                                        <td className="py-1 pr-2 text-right text-blue-800">{fmtK(l.loan_amount)}</td>
                                        <td className="py-1 pr-2 text-blue-700">{l.term_months || '—'} mo</td>
                                        <td className="py-1 pr-2 text-right text-blue-700">{l.rate_pct}%</td>
                                        <td className="py-1 pr-2 text-right text-emerald-700">{fmtK(l.interest_accrued)}</td>
                                        <td className="py-1 pr-2 text-right text-blue-800">{fmtK(l.interest_collected)}</td>
                                        <td className="py-1 pr-2 text-right text-amber-700 font-semibold">{fmtK(l.outstanding)}</td>
                                        <td className="py-1 text-center">
                                          {l.outstanding > 0.01 ? (
                                            <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${agingClass(l.aging_bucket)}`}>
                                              {agingLabel(l.aging_bucket)}
                                            </span>
                                          ) : (
                                            <span className="text-emerald-700 text-[10px] font-semibold">paid</span>
                                          )}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-blue-300 bg-blue-50 font-bold text-blue-900">
                      <td className="py-2 pr-3">All-time</td>
                      <td className="py-2 pr-3 text-right">{data.totals.loans_disbursed_count}</td>
                      <td className="py-2 pr-3 text-right">{fmtK(data.totals.loans_disbursed_amount)}</td>
                      <td className="py-2 pr-3 text-right">{fmtK(data.totals.interest_accrued)}</td>
                      <td className="py-2 pr-3 text-right">{fmtK(data.totals.interest_collected)}</td>
                      <td className="py-2 pr-3 text-right">{fmtK(data.totals.outstanding)}</td>
                      <td className="py-2 text-right">{fmtPct(data.totals.collection_pct)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              <p className="mt-3 text-xs text-blue-700 italic">
                Interest is recognised as income in the loan&apos;s disbursement month
                (accrual basis). &quot;Interest Collected&quot; is cash actually received against
                outstanding receivable in that month. Aging is days since disbursement.
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function Metric({
  label, value, sub, tone,
}: {
  label: string; value: string; sub: string;
  tone: 'blue' | 'emerald' | 'amber' | 'indigo';
}) {
  const bg = {
    blue: 'bg-blue-50 border-blue-200 text-blue-900',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-900',
  }[tone];
  return (
    <div className={`rounded-xl border p-3 ${bg}`}>
      <p className="text-xs font-semibold uppercase tracking-wider opacity-70">{label}</p>
      <p className="text-lg md:text-xl font-bold">{value}</p>
      <p className="text-xs opacity-70">{sub}</p>
    </div>
  );
}
