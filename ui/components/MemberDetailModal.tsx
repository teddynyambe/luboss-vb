'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface DeclarationItems {
  savings_amount: number;
  social_fund: number;
  admin_fund: number;
  penalties: number;
  loan_repayment: number;
  interest_on_loan: number;
}

interface PostedItems {
  savings?: number;
  social_fund?: number;
  admin_fund?: number;
  penalty?: number;
}

interface ReconciliationNote {
  action: string;
  description: string;
  dealing_month: string | null;
}

interface SavingsEntry {
  id: string;
  date: string;
  description: string;
  debit?: number;
  credit?: number;
  amount: number;
  is_declaration?: boolean;
  declaration_items?: DeclarationItems;
  posted_items?: PostedItems;
  has_reconciliation_discrepancy?: boolean;
  reconciliation_notes?: ReconciliationNote[];
  is_excess_transfer?: boolean;
  excess_source?: string;
}

interface RepaymentThisMonth {
  loan_id: string;
  loan_label: string;
  date: string;
  principal: number;
  interest: number;
  total: number;
  was_carved_out: boolean;
  narration: string | null;
}

interface MonthlyLoanBalance {
  month: string;
  loan_balance: number;
  interest_balance: number;
  loans_disbursed_this_month: { loan_id: string; amount: number; expected_interest: number }[];
  repayments_this_month?: RepaymentThisMonth[];
}

interface MemberDetailModalProps {
  open: boolean;
  onClose: () => void;
  memberId: string;
  memberName: string;
}

export default function MemberDetailModal({
  open,
  onClose,
  memberId,
  memberName,
}: MemberDetailModalProps) {
  const [transactions, setTransactions] = useState<SavingsEntry[]>([]);
  const [monthlyLoanBalances, setMonthlyLoanBalances] = useState<MonthlyLoanBalance[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<{
        transactions: SavingsEntry[];
        monthly_loan_balances?: MonthlyLoanBalance[];
      }>(`/api/member/reports/member-savings-history?member_id=${memberId}`);
      if (res.data) {
        setTransactions(res.data.transactions || []);
        setMonthlyLoanBalances(res.data.monthly_loan_balances || []);
      } else {
        setError(res.error || 'Failed to load member data');
      }
    } catch {
      setError('An error occurred while loading data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && memberId) {
      loadData();
    } else {
      setTransactions([]);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, memberId]);

  if (!open) return null;

  const fmt = (n: number | null) =>
    n !== null
      ? `K ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : '—';

  const formatMonth = (dateStr: string) => {
    const [y, m] = dateStr.split('-').map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  };

  // Group entries by month
  const monthMap = new Map<string, {
    month: string;
    declarationItems: DeclarationItems | null;
    postedItems: PostedItems | null;
    hasDiscrepancy: boolean;
    reconciliationNotes: ReconciliationNote[];
    deposited: number | null;
  }>();
  for (const entry of transactions) {
    const key = entry.date.substring(0, 7);
    if (!monthMap.has(key)) {
      monthMap.set(key, {
        month: entry.date,
        declarationItems: null,
        postedItems: null,
        hasDiscrepancy: false,
        reconciliationNotes: [],
        deposited: null,
      });
    }
    const row = monthMap.get(key)!;
    if (entry.is_declaration) {
      row.declarationItems = entry.declaration_items ?? null;
      row.postedItems = entry.posted_items ?? null;
      row.hasDiscrepancy = !!entry.has_reconciliation_discrepancy;
      row.reconciliationNotes = entry.reconciliation_notes ?? [];
    } else {
      row.deposited = (row.deposited ?? 0) + entry.amount;
    }
  }
  const rows = Array.from(monthMap.values()).sort((a, b) => a.month.localeCompare(b.month));
  const totalDeclared = rows.reduce((s, r) => {
    if (!r.declarationItems) return s;
    return s + Object.values(r.declarationItems).reduce((a, b) => a + b, 0);
  }, 0);
  const totalDeposited = rows.reduce((s, r) => s + (r.deposited ?? 0), 0);

  const balanceByMonth = new Map<string, MonthlyLoanBalance>();
  for (const b of monthlyLoanBalances) {
    balanceByMonth.set(b.month.substring(0, 7), b);
  }
  const hasAnyLoanActivity = monthlyLoanBalances.some(
    (b) => b.loan_balance > 0 || b.interest_balance > 0 || b.loans_disbursed_this_month.length > 0,
  );

  // Contribution summary — uses the LIVE per-month posted amounts when
  // available (so splits/reverses on the ledger are reflected) and falls
  // back to declared figures when not. Matches the Account Status cards on
  // the Member Dashboard.
  const totals = transactions.reduce(
    (acc, entry) => {
      if (entry.is_declaration && entry.declaration_items) {
        const p = entry.posted_items;
        acc.savings += p?.savings ?? entry.declaration_items.savings_amount;
        acc.social_fund += p?.social_fund ?? entry.declaration_items.social_fund;
        acc.admin_fund += p?.admin_fund ?? entry.declaration_items.admin_fund;
        acc.penalties += p?.penalty ?? entry.declaration_items.penalties;
      }
      // Excess transfers and treasurer adjustments are already in posted_items.
      return acc;
    },
    { savings: 0, social_fund: 0, admin_fund: 0, penalties: 0 }
  );
  const grand = totals.savings + totals.social_fund + totals.admin_fund + totals.penalties;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="member-detail-title"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[90vh] rounded-xl border-2 border-blue-300 bg-white shadow-xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white p-5 md:p-6">
          <div className="flex items-center justify-between">
            <h2 id="member-detail-title" className="text-xl md:text-2xl font-bold">
              {memberName}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="text-white hover:text-blue-200 transition-colors focus:outline-none focus:ring-2 focus:ring-white rounded-full p-1"
              aria-label="Close modal"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 md:p-6 space-y-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading member data...</p>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <div className="mb-4">
                <svg className="mx-auto h-16 w-16 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-red-700 text-lg font-medium">{error}</p>
              <button
                onClick={loadData}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : transactions.length === 0 ? (
            <div className="text-center py-12">
              <div className="mb-4">
                <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-gray-600 text-lg font-medium">No savings history</p>
              <p className="text-gray-500 text-sm mt-2">This member has no savings transactions yet.</p>
            </div>
          ) : (
            <>
              {/* Savings History Table */}
              <div>
                <h3 className="text-lg font-bold text-blue-900 mb-3">Savings History</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b-2 border-blue-200">
                        <th className="text-left py-2 pr-4 text-blue-700 font-semibold">Month</th>
                        <th className="text-right py-2 pr-4 text-blue-700 font-semibold">Declaration</th>
                        <th className="text-right py-2 pr-4 text-blue-700 font-semibold whitespace-nowrap">Approved Deposit</th>
                        {hasAnyLoanActivity && (
                          <>
                            <th
                              className="text-right py-2 pr-4 text-blue-700 font-semibold whitespace-nowrap"
                              title="Outstanding loan principal at end of month"
                            >
                              Loan Balance
                            </th>
                            <th
                              className="text-right py-2 text-blue-700 font-semibold whitespace-nowrap"
                              title="Outstanding interest receivable at end of month — full interest accrued in borrowing month"
                            >
                              Interest Balance
                            </th>
                          </>
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-blue-100">
                      {rows.map((row) => (
                        <tr key={row.month}>
                          <td className="py-2 pr-4 text-blue-800 whitespace-nowrap">
                            {formatMonth(row.month)}
                            {row.hasDiscrepancy && (
                              <span
                                className="ml-2 text-amber-600"
                                title={
                                  row.reconciliationNotes.length > 0
                                    ? row.reconciliationNotes
                                        .map((n) => `${n.action}: ${n.description}`)
                                        .join('\n')
                                    : "Posted amounts differ from declared due to treasurer reconciliation."
                                }
                              >
                                🔧
                              </span>
                            )}
                          </td>
                          <td className="py-2 pr-4 text-right text-blue-700">
                            {row.declarationItems ? (
                              <div className="text-xs space-y-0.5 leading-5">
                                {(() => {
                                  type Row = { label: string; declared: number; posted?: number };
                                  const items: Row[] = [
                                    { label: 'Savings',        declared: row.declarationItems.savings_amount, posted: row.postedItems?.savings },
                                    { label: 'Social Fund',    declared: row.declarationItems.social_fund,    posted: row.postedItems?.social_fund },
                                    { label: 'Admin Fund',     declared: row.declarationItems.admin_fund,     posted: row.postedItems?.admin_fund },
                                    { label: 'Penalties',      declared: row.declarationItems.penalties,      posted: row.postedItems?.penalty },
                                    { label: 'Loan Repayment', declared: row.declarationItems.loan_repayment },
                                    { label: 'Interest',       declared: row.declarationItems.interest_on_loan },
                                  ];
                                  return items.map((it) => {
                                    const decl = it.declared || 0;
                                    const post = it.posted;
                                    const differs = post !== undefined && Math.abs(post - decl) > 0.01;
                                    if (decl <= 0 && !(differs && post)) return null;
                                    if (!differs) {
                                      return (
                                        <div key={it.label}>
                                          <span className="text-blue-500">{it.label}:</span> {fmt(decl)}
                                        </div>
                                      );
                                    }
                                    return (
                                      <div key={it.label} title="Posted via treasurer reconciliation">
                                        <span className="text-blue-500">{it.label}:</span>{' '}
                                        <span className="text-gray-500 line-through">{fmt(decl)}</span>
                                        <span className="text-blue-500"> declared</span>
                                        <span className="mx-1 text-amber-600">→</span>
                                        <span className="font-semibold text-amber-700">{fmt(post)}</span>
                                        <span className="text-amber-700"> posted</span>
                                      </div>
                                    );
                                  });
                                })()}
                                {row.reconciliationNotes.length > 0 && (
                                  <div className="mt-1 pt-1 border-t border-amber-200 text-[11px] text-amber-700 space-y-0.5 leading-tight">
                                    {row.reconciliationNotes.map((n, i) => (
                                      <div key={i} className="text-left">
                                        <span className="font-semibold">{n.action}:</span> {n.description}
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {(() => {
                                  const bal = balanceByMonth.get(row.month.substring(0, 7));
                                  const reps = bal?.repayments_this_month ?? [];
                                  if (reps.length === 0) return null;
                                  return (
                                    <div className="mt-1 pt-1 border-t border-blue-200 text-[11px] text-blue-700 space-y-0.5 leading-tight text-left">
                                      <div className="font-semibold text-blue-800">Posted to loans:</div>
                                      {reps.map((r, i) => (
                                        <div key={i} className={r.was_carved_out ? 'text-amber-700' : ''}>
                                          <span className="font-semibold">{r.loan_label}:</span>{' '}
                                          {r.principal > 0 && <span>P {fmt(r.principal)}</span>}
                                          {r.principal > 0 && r.interest > 0 && <span> · </span>}
                                          {r.interest > 0 && <span>I {fmt(r.interest)}</span>}
                                          {r.was_carved_out && (
                                            <span
                                              className="ml-1 text-amber-700"
                                              title={r.narration || 'Moved by treasurer'}
                                            >
                                              (moved by treasurer)
                                            </span>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  );
                                })()}
                              </div>
                            ) : (() => {
                              // No declaration row for this month but a carve-out repayment
                              // may still have landed here (e.g. interest moved in from
                              // another loan). Show those so the member sees the activity.
                              const bal = balanceByMonth.get(row.month.substring(0, 7));
                              const reps = bal?.repayments_this_month ?? [];
                              if (reps.length === 0) return '—';
                              return (
                                <div className="text-[11px] text-blue-700 space-y-0.5 leading-tight text-left">
                                  <div className="font-semibold text-blue-800">Posted to loans:</div>
                                  {reps.map((r, i) => (
                                    <div key={i} className={r.was_carved_out ? 'text-amber-700' : ''}>
                                      <span className="font-semibold">{r.loan_label}:</span>{' '}
                                      {r.principal > 0 && <span>P {fmt(r.principal)}</span>}
                                      {r.principal > 0 && r.interest > 0 && <span> · </span>}
                                      {r.interest > 0 && <span>I {fmt(r.interest)}</span>}
                                      {r.was_carved_out && (
                                        <span
                                          className="ml-1 text-amber-700"
                                          title={r.narration || 'Moved by treasurer'}
                                        >
                                          (moved by treasurer)
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              );
                            })()}
                          </td>
                          <td className="py-2 pr-4 text-right font-semibold text-blue-900 whitespace-nowrap align-top">{fmt(row.deposited)}</td>
                          {hasAnyLoanActivity && (() => {
                            const bal = balanceByMonth.get(row.month.substring(0, 7));
                            const disbursedHere = bal?.loans_disbursed_this_month ?? [];
                            return (
                              <>
                                <td className="py-2 pr-4 text-right text-blue-800 whitespace-nowrap align-top">
                                  {bal ? fmt(bal.loan_balance) : '—'}
                                  {disbursedHere.length > 0 && (
                                    <div className="text-[10px] font-normal text-emerald-700 mt-0.5">
                                      +{disbursedHere.map((l) => fmt(l.amount)).join(', ')} new
                                    </div>
                                  )}
                                </td>
                                <td className="py-2 text-right text-blue-800 whitespace-nowrap align-top">
                                  {bal ? fmt(bal.interest_balance) : '—'}
                                  {disbursedHere.length > 0 && disbursedHere.some((l) => l.expected_interest > 0) && (
                                    <div className="text-[10px] font-normal text-emerald-700 mt-0.5">
                                      +{disbursedHere
                                        .filter((l) => l.expected_interest > 0)
                                        .map((l) => fmt(l.expected_interest))
                                        .join(', ')} accrued
                                    </div>
                                  )}
                                </td>
                              </>
                            );
                          })()}
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-blue-300 bg-blue-50">
                        <td className="py-2 pr-4 font-bold text-blue-900">Total</td>
                        <td className="py-2 pr-4 text-right font-bold text-blue-900 whitespace-nowrap">{fmt(totalDeclared)}</td>
                        <td className="py-2 pr-4 text-right font-bold text-blue-900 whitespace-nowrap">{fmt(totalDeposited)}</td>
                        {hasAnyLoanActivity && (
                          <>
                            <td className="py-2 pr-4 text-right text-blue-700 whitespace-nowrap text-xs italic">running</td>
                            <td className="py-2 text-right text-blue-700 whitespace-nowrap text-xs italic">running</td>
                          </>
                        )}
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              {/* Contribution Summary */}
              <div>
                <h3 className="text-lg font-bold text-blue-900 mb-3">Contribution Summary</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
                  <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
                    <p className="text-xs font-semibold text-blue-500 uppercase tracking-wider mb-2">Savings</p>
                    <p className="text-base md:text-lg font-bold text-blue-900">{fmt(totals.savings)}</p>
                  </div>
                  <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-center">
                    <p className="text-xs font-semibold text-indigo-500 uppercase tracking-wider mb-2">Social Fund</p>
                    <p className="text-base md:text-lg font-bold text-indigo-900">{fmt(totals.social_fund)}</p>
                  </div>
                  <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 text-center">
                    <p className="text-xs font-semibold text-violet-500 uppercase tracking-wider mb-2">Admin Fund</p>
                    <p className="text-base md:text-lg font-bold text-violet-900">{fmt(totals.admin_fund)}</p>
                  </div>
                  <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
                    <p className="text-xs font-semibold text-red-500 uppercase tracking-wider mb-2">Penalties</p>
                    <p className="text-base md:text-lg font-bold text-red-900">{fmt(totals.penalties)}</p>
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t-2 border-blue-200 flex justify-between items-center">
                  <span className="text-sm font-semibold text-blue-700 uppercase tracking-wide">Total Contributions</span>
                  <span className="text-xl font-bold text-blue-900">{fmt(grand)}</span>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 bg-gray-50 p-5 md:p-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
