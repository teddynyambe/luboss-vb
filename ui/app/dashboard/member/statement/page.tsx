'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface BankStatementItem {
  id: string;
  cycle_id: string;
  statement_month: string;   // "YYYY-MM-DD"
  description: string | null;
  filename: string;
  uploaded_at: string | null;
}

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
  date: string;        // "YYYY-MM-DD" or ISO
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
  excess_source?: string; // "social_fund" | "admin_fund"
  // Set when this row represents a reversed penalty being credited back
  // to the member's savings account (Dr PENALTY_INCOME / Cr MEM_SAV).
  is_penalty_reversal?: boolean;
  penalty_type_name?: string;
  fee_amount?: number;
  reversal_reason?: string | null;
  reversed_at?: string | null;
  original_date_issued?: string | null;
}

interface PenaltyReversal {
  id: string;
  penalty_type_name: string;
  fee_amount: number;
  reversed_at: string | null;
  reversal_reason: string | null;
  original_date_issued: string | null;
}

interface LiveBalances {
  savings: number;
  social_fund: number;
  admin_fund: number;
  penalties: number;
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
  month: string;           // "YYYY-MM-DD" (first of month)
  loan_balance: number;
  interest_balance: number;
  loans_disbursed_this_month: { loan_id: string; amount: number; expected_interest: number }[];
  repayments_this_month?: RepaymentThisMonth[];
}

export default function MemberStatementPage() {
  const [bankStatements, setBankStatements] = useState<BankStatementItem[]>([]);
  const [savingsHistory, setSavingsHistory] = useState<SavingsEntry[]>([]);
  const [penaltyReversals, setPenaltyReversals] = useState<PenaltyReversal[]>([]);
  // Live balances from the backend (same source as the member's Account
  // Status card and Penalty Audit modal). Used for the Contribution
  // Summary tiles so all three views agree on the numbers.
  const [liveBalances, setLiveBalances] = useState<LiveBalances | null>(null);
  const [monthlyLoanBalances, setMonthlyLoanBalances] = useState<MonthlyLoanBalance[]>([]);
  const [loading, setLoading] = useState(true);

  // PDF viewer state
  const [showFileModal, setShowFileModal] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileBlobUrl, setFileBlobUrl] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [currentFilename, setCurrentFilename] = useState<string>('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const [stmtsRes, savingsRes] = await Promise.all([
      api.get<{ statements: BankStatementItem[] }>('/api/member/bank-statements'),
      api.get<{
        type: string;
        transactions: SavingsEntry[];
        monthly_loan_balances?: MonthlyLoanBalance[];
        penalty_reversals?: PenaltyReversal[];
        live_balances?: LiveBalances | null;
      }>('/api/member/transactions?type=savings'),
    ]);

    if (stmtsRes.data) setBankStatements(stmtsRes.data.statements);
    if (savingsRes.data) {
      setSavingsHistory(savingsRes.data.transactions);
      setMonthlyLoanBalances(savingsRes.data.monthly_loan_balances || []);
      setPenaltyReversals(savingsRes.data.penalty_reversals || []);
      setLiveBalances(savingsRes.data.live_balances ?? null);
    }
    setLoading(false);
  };

  const formatMonth = (dateString: string) => {
    const datePart = dateString.split('T')[0].split(' ')[0];
    const [year, month] = datePart.split('-').map(Number);
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    if (month >= 1 && month <= 12 && year) {
      return `${monthNames[month - 1]} ${year}`;
    }
    return dateString;
  };

  const getFileExtension = (filename: string): string => {
    return filename.split('.').pop()?.toLowerCase() || '';
  };

  const isImage = (filename: string): boolean => {
    return ['jpg', 'jpeg', 'png', 'gif'].includes(getFileExtension(filename));
  };

  const handleViewStatement = async (stmt: BankStatementItem) => {
    setCurrentFilename(stmt.filename);
    setFileLoading(true);
    setFileError(null);
    setFileBlobUrl(null);
    setShowFileModal(true);

    try {
      const blobUrl = await api.getFileBlob(
        `/api/member/bank-statements/file/${encodeURIComponent(stmt.filename)}`
      );
      setFileBlobUrl(blobUrl);
    } catch (error) {
      setFileError(error instanceof Error ? error.message : 'Failed to load file');
    } finally {
      setFileLoading(false);
    }
  };

  const closeFileModal = () => {
    setShowFileModal(false);
    if (fileBlobUrl) {
      URL.revokeObjectURL(fileBlobUrl);
      setFileBlobUrl(null);
    }
    setFileError(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">My Statement</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-6">
        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <p className="mt-4 text-blue-700 text-lg">Loading...</p>
          </div>
        ) : (
          <>
            {/* Bank Statements Card */}
            <div className="card">
              <h2 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Bank Statements</h2>
              {bankStatements.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No bank statements available for the current cycle.</p>
              ) : (
                <div className="space-y-2">
                  {bankStatements.map((stmt) => (
                    <div
                      key={stmt.id}
                      className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-blue-900 text-sm">{formatMonth(stmt.statement_month)}</p>
                        {stmt.description && (
                          <p className="text-xs text-blue-600 truncate">{stmt.description}</p>
                        )}
                      </div>
                      <button
                        onClick={() => handleViewStatement(stmt)}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition-colors flex-shrink-0"
                      >
                        View PDF
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* My Savings History Card */}
            <div className="card">
              <h2 className="text-lg md:text-xl font-bold text-blue-900 mb-4">My Savings History</h2>
              {savingsHistory.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No savings history available.</p>
              ) : (() => {
                // Group entries by month key (YYYY-MM), keeping declaration and deposit separately
                const monthMap = new Map<string, {
                  month: string;
                  declarationItems: DeclarationItems | null;
                  postedItems: PostedItems | null;
                  hasDiscrepancy: boolean;
                  reconciliationNotes: ReconciliationNote[];
                  deposited: number | null;
                  penaltyReversalsInMonth: {
                    id: string;
                    penalty_type_name: string;
                    fee_amount: number;
                    reversal_reason: string | null;
                    reversed_at: string | null;
                  }[];
                }>();
                for (const entry of savingsHistory) {
                  const key = entry.date.substring(0, 7); // "YYYY-MM"
                  if (!monthMap.has(key)) {
                    monthMap.set(key, {
                      month: entry.date,
                      declarationItems: null,
                      postedItems: null,
                      hasDiscrepancy: false,
                      reconciliationNotes: [],
                      deposited: null,
                      penaltyReversalsInMonth: [],
                    });
                  }
                  const row = monthMap.get(key)!;
                  if (entry.is_declaration) {
                    row.declarationItems = entry.declaration_items ?? null;
                    row.postedItems = entry.posted_items ?? null;
                    row.hasDiscrepancy = !!entry.has_reconciliation_discrepancy;
                    row.reconciliationNotes = entry.reconciliation_notes ?? [];
                  } else if (entry.is_penalty_reversal) {
                    // Reversals are neither declarations nor deposits — track
                    // them separately so we can render a clear "penalty
                    // refunded" line in the month row without inflating the
                    // Approved Deposit total.
                    row.penaltyReversalsInMonth.push({
                      id: entry.id,
                      penalty_type_name: entry.penalty_type_name || 'Penalty',
                      fee_amount: entry.fee_amount || entry.amount || 0,
                      reversal_reason: entry.reversal_reason ?? null,
                      reversed_at: entry.reversed_at ?? entry.date,
                    });
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
                const fmt = (n: number | null) =>
                  n !== null ? `K ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';

                // Loan/interest balances keyed by "YYYY-MM" for fast lookup per row
                const balanceByMonth = new Map<string, MonthlyLoanBalance>();
                for (const b of monthlyLoanBalances) {
                  balanceByMonth.set(b.month.substring(0, 7), b);
                }
                const hasAnyLoanActivity = monthlyLoanBalances.some(
                  (b) => b.loan_balance > 0 || b.interest_balance > 0 || b.loans_disbursed_this_month.length > 0,
                );

                return (
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
                                title="Outstanding loan principal at end of month (running balance)"
                              >
                                Loan Balance
                              </th>
                              <th
                                className="text-right py-2 text-blue-700 font-semibold whitespace-nowrap"
                                title="Outstanding interest receivable at end of month — full interest is accrued in the borrowing month and drawn down by payments"
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
                            <td className="py-2 pr-4 text-blue-800 whitespace-nowrap align-top">
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
                                  ⚙
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
                                      // When there's no discrepancy, show one figure.
                                      // When declared and posted differ, label both explicitly
                                      // with strike-through on the declared so it can't be
                                      // misread as the live amount.
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
                                  {/* Penalty reversals credited back to savings
                                      in this month — each shows fee + reason so
                                      the member sees the refund explicitly. */}
                                  {row.penaltyReversalsInMonth.length > 0 && (
                                    <div className="mt-1 pt-1 border-t border-emerald-200 text-[11px] text-emerald-800 space-y-0.5 leading-tight text-left">
                                      <div className="font-semibold text-emerald-800">Penalty refunded to savings:</div>
                                      {row.penaltyReversalsInMonth.map((pr) => (
                                        <div key={pr.id} title={pr.reversal_reason ?? undefined}>
                                          <span className="font-semibold">{pr.penalty_type_name}:</span>{' '}
                                          +K{pr.fee_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                          {pr.reversal_reason && (
                                            <span className="ml-1 italic text-emerald-700">
                                              — {pr.reversal_reason}
                                            </span>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ) : (() => {
                                const bal = balanceByMonth.get(row.month.substring(0, 7));
                                const reps = bal?.repayments_this_month ?? [];
                                if (reps.length === 0 && row.penaltyReversalsInMonth.length === 0) return '—';
                                return (
                                  <div className="text-[11px] text-blue-700 space-y-0.5 leading-tight text-left">
                                    {reps.length > 0 && (
                                      <>
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
                                      </>
                                    )}
                                    {row.penaltyReversalsInMonth.length > 0 && (
                                      <div className={reps.length > 0 ? 'mt-1 pt-1 border-t border-emerald-200' : ''}>
                                        <div className="font-semibold text-emerald-800">Penalty refunded to savings:</div>
                                        {row.penaltyReversalsInMonth.map((pr) => (
                                          <div key={pr.id} className="text-emerald-700" title={pr.reversal_reason ?? undefined}>
                                            <span className="font-semibold">{pr.penalty_type_name}:</span>{' '}
                                            +K{pr.fee_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            {pr.reversal_reason && (
                                              <span className="ml-1 italic">— {pr.reversal_reason}</span>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    )}
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
                              <td className="py-2 pr-4 text-right text-blue-700 whitespace-nowrap text-xs italic">
                                running
                              </td>
                              <td className="py-2 text-right text-blue-700 whitespace-nowrap text-xs italic">
                                running
                              </td>
                            </>
                          )}
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                );
              })()}
            </div>

            {/* Contribution Summary Card — reflects the LIVE ledger balance
                (credits − debits) per category, so it matches the Account
                Status cards on the Member Dashboard. After a treasurer split
                or reverse, the posted amounts diverge from the originally
                declared figures; this summary follows the actual money. */}
            {savingsHistory.length > 0 && (() => {
              const totals = savingsHistory.reduce(
                (acc, entry) => {
                  if (entry.is_declaration && entry.declaration_items) {
                    // Prefer posted (live) per-month amounts when present so
                    // splits/reverses on the ledger are reflected here.
                    const p = entry.posted_items;
                    acc.savings += p?.savings ?? entry.declaration_items.savings_amount;
                    acc.social_fund += p?.social_fund ?? entry.declaration_items.social_fund;
                    acc.admin_fund += p?.admin_fund ?? entry.declaration_items.admin_fund;
                    acc.penalties += p?.penalty ?? entry.declaration_items.penalties;
                  }
                  // Note: excess transfers and treasurer-adjustment lines are
                  // already baked into posted_items, so they don't need a
                  // separate branch here.
                  return acc;
                },
                { savings: 0, social_fund: 0, admin_fund: 0, penalties: 0 }
              );
              // Prefer live balances from the backend when available so the
              // Contribution Summary matches exactly what the member sees on
              // their Account Status card and Penalty Audit modal. Falls
              // back to declared totals only when the backend didn't ship
              // the live_balances field (older backends, or query errors).
              const totalReversedPenalties = penaltyReversals.reduce(
                (s, r) => s + (r.fee_amount || 0), 0,
              );
              if (liveBalances) {
                totals.savings = liveBalances.savings;
                totals.social_fund = liveBalances.social_fund;
                totals.admin_fund = liveBalances.admin_fund;
                totals.penalties = liveBalances.penalties;
              } else {
                // Legacy fallback: adjust declared totals by reversals.
                totals.savings += totalReversedPenalties;
                totals.penalties = Math.max(0, totals.penalties - totalReversedPenalties);
              }
              const fmtS = (n: number) =>
                `K ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
              const grand = totals.savings + totals.social_fund + totals.admin_fund + totals.penalties;

              return (
                <div className="card">
                  <h2 className="text-lg md:text-xl font-bold text-blue-900 mb-5">Contribution Summary</h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
                    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
                      <p className="text-xs font-semibold text-blue-500 uppercase tracking-wider mb-2">Savings</p>
                      <p className="text-base md:text-lg font-bold text-blue-900">{fmtS(totals.savings)}</p>
                      {totalReversedPenalties > 0 && (
                        <p className="text-[10px] text-emerald-700 mt-1">
                          Includes {fmtS(totalReversedPenalties)} refunded from reversed penalties
                        </p>
                      )}
                    </div>
                    <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-center">
                      <p className="text-xs font-semibold text-indigo-500 uppercase tracking-wider mb-2">Social Fund</p>
                      <p className="text-base md:text-lg font-bold text-indigo-900">{fmtS(totals.social_fund)}</p>
                    </div>
                    <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 text-center">
                      <p className="text-xs font-semibold text-violet-500 uppercase tracking-wider mb-2">Admin Fund</p>
                      <p className="text-base md:text-lg font-bold text-violet-900">{fmtS(totals.admin_fund)}</p>
                    </div>
                    <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
                      <p className="text-xs font-semibold text-red-500 uppercase tracking-wider mb-2">Penalties</p>
                      <p className="text-base md:text-lg font-bold text-red-900">{fmtS(totals.penalties)}</p>
                      {totalReversedPenalties > 0 && (
                        <p className="text-[10px] text-red-700 mt-1">
                          Net after {fmtS(totalReversedPenalties)} reversed
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-5 pt-4 border-t-2 border-blue-200 flex justify-between items-center">
                    <span className="text-sm font-semibold text-blue-700 uppercase tracking-wide">Total Contributions</span>
                    <span className="text-xl font-bold text-blue-900">{fmtS(grand)}</span>
                  </div>
                </div>
              );
            })()}
          </>
        )}
      </main>

      {/* File Viewer Modal */}
      {showFileModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50"
          onClick={closeFileModal}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[95vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl font-bold">Bank Statement</h2>
              <button
                onClick={closeFileModal}
                className="text-white hover:text-blue-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6 bg-gray-100">
              {fileLoading ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4" />
                    <p className="text-blue-700 text-lg">Loading file...</p>
                  </div>
                </div>
              ) : fileError ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="text-red-500 text-5xl mb-4">⚠️</div>
                    <p className="text-red-700 text-lg font-semibold">{fileError}</p>
                    <button
                      onClick={closeFileModal}
                      className="mt-4 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : fileBlobUrl ? (
                <div className="w-full h-full">
                  {isImage(currentFilename) ? (
                    <div className="flex items-center justify-center min-h-[500px]">
                      <img
                        src={fileBlobUrl}
                        alt="Bank Statement"
                        className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-lg"
                      />
                    </div>
                  ) : (
                    <div className="w-full h-[80vh]">
                      <iframe
                        src={fileBlobUrl}
                        className="w-full h-full border-0 rounded-lg shadow-lg"
                        title="Bank Statement"
                      />
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {fileBlobUrl && (
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <p className="text-sm text-gray-600">{currentFilename}</p>
                <div className="flex gap-3">
                  <a
                    href={fileBlobUrl}
                    download={currentFilename}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                  >
                    Download
                  </a>
                  <button
                    onClick={closeFileModal}
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
    </div>
  );
}
