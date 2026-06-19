'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

interface Repayment {
  id: string;
  loan_id: string | null;
  repayment_date: string | null;
  principal_amount: number;
  interest_amount: number;
  total_amount: number;
  journal_entry_id: string | null;
  is_live: boolean;
}

interface LoanRow {
  id: string;
  loan_amount: number;
  percentage_interest: number;
  number_of_instalments: string | null;
  disbursement_date: string | null;
  loan_status: string | null;
  application_id: string | null;
  has_live_disbursement_je: boolean;
  ledger_disbursed: number;
  live_principal_paid: number;
  live_interest_paid: number;
  outstanding: number;
  expected_interest: number;
  interest_outstanding: number;
  created_at: string | null;
  repayments: Repayment[];
}

interface LoanState {
  member_id: string;
  loans: LoanRow[];
  summary: {
    active_loan_count: number;
    ledger_disbursed_net: number;
    ledger_repayments_principal: number;
    ledger_outstanding: number;
    interest_expected_total: number;
    interest_paid_total: number;
    interest_outstanding_total: number;
  };
}

const isActive = (status: string | null) =>
  status === 'open' || status === 'disbursed' || status === 'approved';

const fmt = (n: number) =>
  `K${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function LoanStatePanel({ memberId }: { memberId: string }) {
  const [state, setState] = useState<LoanState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Consolidate modal state
  const [showConsolidate, setShowConsolidate] = useState(false);
  const [keepId, setKeepId] = useState('');
  const [newAmount, setNewAmount] = useState('');
  const [newRate, setNewRate] = useState('');
  const [newTerm, setNewTerm] = useState('');
  const [closeIds, setCloseIds] = useState<string[]>([]);
  const [consolidating, setConsolidating] = useState(false);

  // Edit-split modal state
  const [editRep, setEditRep] = useState<Repayment | null>(null);
  const [editPrincipal, setEditPrincipal] = useState('');
  const [editInterest, setEditInterest] = useState('');
  const [savingSplit, setSavingSplit] = useState(false);

  // Move-repayment modal state
  const [moveRep, setMoveRep] = useState<Repayment | null>(null);
  const [moveTargetLoanId, setMoveTargetLoanId] = useState('');
  const [movingRep, setMovingRep] = useState(false);

  // Reverse-repayment modal state
  const [reverseRep, setReverseRep] = useState<Repayment | null>(null);
  const [reversing, setReversing] = useState(false);

  // Per-loan repair menu/modal state
  type RepairAction =
    | 'reopen'
    | 'close'
    | 'reverse_disbursement'
    | 'restore_disbursement'
    | 'reverse_all_reps'
    | 'move_all_reps'
    | 'edit_disbursement_date'
    | 'edit_terms';
  const [openMenuLoanId, setOpenMenuLoanId] = useState<string | null>(null);
  const [repairLoan, setRepairLoan] = useState<LoanRow | null>(null);
  const [repairAction, setRepairAction] = useState<RepairAction | null>(null);
  const [repairReason, setRepairReason] = useState('');
  const [repairTargetLoanId, setRepairTargetLoanId] = useState('');
  const [repairNewDate, setRepairNewDate] = useState('');
  const [repairNewTerm, setRepairNewTerm] = useState('');
  const [repairNewRate, setRepairNewRate] = useState('');
  const [repairNewAmount, setRepairNewAmount] = useState('');
  const [submittingRepair, setSubmittingRepair] = useState(false);

  const load = useCallback(() => {
    if (!memberId) {
      setState(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .get<LoanState>(`/api/chairman/reconcile/loan-state/${memberId}`)
      .then((res) => {
        if (res.data) setState(res.data);
        else setError(res.error || 'Failed to load loan state');
      })
      .finally(() => setLoading(false));
  }, [memberId]);

  useEffect(() => {
    load();
  }, [load]);

  const openConsolidate = () => {
    if (!state) return;
    const active = state.loans.filter((l) => isActive(l.loan_status));
    if (active.length < 2) return;
    // Default keep = the one with application_id, else the first active
    const preferred =
      active.find((l) => l.application_id) || active[0];
    setKeepId(preferred.id);
    setNewAmount(String(preferred.loan_amount));
    setNewRate(String(preferred.percentage_interest));
    setNewTerm(preferred.number_of_instalments || '');
    setCloseIds(active.filter((l) => l.id !== preferred.id).map((l) => l.id));
    setShowConsolidate(true);
  };

  const toggleCloseId = (id: string) => {
    setCloseIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const submitConsolidate = async () => {
    if (!keepId || closeIds.length === 0) return;
    setConsolidating(true);
    try {
      const res = await api.post('/api/chairman/reconcile/consolidate', {
        member_id: memberId,
        keep_loan_id: keepId,
        new_loan_amount: parseFloat(newAmount) || 0,
        new_percentage_interest: newRate === '' ? null : parseFloat(newRate),
        new_number_of_instalments: newTerm || null,
        close_loan_ids: closeIds,
      });
      if (res.error) {
        setError(res.error);
      } else {
        setShowConsolidate(false);
        load();
      }
    } finally {
      setConsolidating(false);
    }
  };

  const openEditSplit = (rep: Repayment) => {
    setEditRep(rep);
    setEditPrincipal(String(rep.principal_amount));
    setEditInterest(String(rep.interest_amount));
  };

  const confirmReverseRepayment = async () => {
    if (!reverseRep) return;
    setReversing(true);
    try {
      const res = await api.post(
        `/api/chairman/reconcile/repayment/${reverseRep.id}/reverse`,
        {}
      );
      if (res.error) setError(res.error);
      else {
        setReverseRep(null);
        load();
      }
    } finally {
      setReversing(false);
    }
  };

  const openMoveRepayment = (rep: Repayment) => {
    setMoveRep(rep);
    setMoveTargetLoanId('');
  };

  const submitMoveRepayment = async () => {
    if (!moveRep || !moveTargetLoanId) return;
    setMovingRep(true);
    try {
      const res = await api.post(
        `/api/chairman/reconcile/repayment/${moveRep.id}/move`,
        { new_loan_id: moveTargetLoanId }
      );
      if (res.error) setError(res.error);
      else {
        setMoveRep(null);
        load();
      }
    } finally {
      setMovingRep(false);
    }
  };

  const submitEditSplit = async () => {
    if (!editRep) return;
    setSavingSplit(true);
    try {
      const res = await api.patch(
        `/api/chairman/reconcile/repayment/${editRep.id}`,
        {
          new_principal: parseFloat(editPrincipal) || 0,
          new_interest: parseFloat(editInterest) || 0,
        }
      );
      if (res.error) {
        setError(res.error);
      } else {
        setEditRep(null);
        load();
      }
    } finally {
      setSavingSplit(false);
    }
  };

  const openRepair = (loan: LoanRow, action: RepairAction) => {
    setRepairLoan(loan);
    setRepairAction(action);
    setRepairReason('');
    setRepairTargetLoanId('');
    setRepairNewDate(action === 'edit_disbursement_date' ? (loan.disbursement_date || '') : '');
    setRepairNewTerm(action === 'edit_terms' ? (loan.number_of_instalments || '') : '');
    setRepairNewRate(action === 'edit_terms' ? String(loan.percentage_interest ?? '') : '');
    setRepairNewAmount(action === 'edit_terms' ? String(loan.loan_amount ?? '') : '');
    setOpenMenuLoanId(null);
  };

  const closeRepair = () => {
    setRepairLoan(null);
    setRepairAction(null);
    setRepairReason('');
    setRepairTargetLoanId('');
    setRepairNewDate('');
    setRepairNewTerm('');
    setRepairNewRate('');
    setRepairNewAmount('');
  };

  const submitRepair = async () => {
    if (!repairLoan || !repairAction) return;
    const reason = repairReason.trim();
    if (reason.length < 5) {
      setError('Please provide a reason (at least 5 characters).');
      return;
    }
    setSubmittingRepair(true);
    setError(null);
    try {
      let res;
      const base = `/api/chairman/reconcile/loan/${repairLoan.id}`;
      if (repairAction === 'reopen') {
        res = await api.post(`${base}/reopen`, { reason });
      } else if (repairAction === 'close') {
        res = await api.post(`${base}/close`, { reason });
      } else if (repairAction === 'reverse_disbursement') {
        res = await api.post(`${base}/reverse-disbursement`, { reason });
      } else if (repairAction === 'restore_disbursement') {
        res = await api.post(`${base}/restore-disbursement`, { reason });
      } else if (repairAction === 'reverse_all_reps') {
        res = await api.post(`${base}/reverse-all-repayments`, { reason });
      } else if (repairAction === 'move_all_reps') {
        if (!repairTargetLoanId) {
          setError('Pick a destination loan.');
          setSubmittingRepair(false);
          return;
        }
        res = await api.post(`${base}/move-all-repayments`, {
          new_loan_id: repairTargetLoanId,
          reason,
        });
      } else if (repairAction === 'edit_disbursement_date') {
        if (!repairNewDate) {
          setError('Pick a new disbursement date.');
          setSubmittingRepair(false);
          return;
        }
        res = await api.post(`${base}/edit-disbursement-date`, {
          new_disbursement_date: repairNewDate,
          reason,
        });
      } else if (repairAction === 'edit_terms') {
        const termChanged = repairNewTerm && repairNewTerm !== (repairLoan.number_of_instalments || '');
        const rateChanged =
          repairNewRate !== '' &&
          parseFloat(repairNewRate) !== (repairLoan.percentage_interest ?? NaN);
        const amountChanged =
          repairNewAmount !== '' &&
          parseFloat(repairNewAmount) !== (repairLoan.loan_amount ?? NaN);
        if (!termChanged && !rateChanged && !amountChanged) {
          setError('Change the loan amount, tenure, or interest rate before saving.');
          setSubmittingRepair(false);
          return;
        }
        res = await api.post(`${base}/edit-terms`, {
          new_term_months: termChanged ? repairNewTerm : null,
          new_percentage_interest: rateChanged ? parseFloat(repairNewRate) : null,
          new_loan_amount: amountChanged ? parseFloat(repairNewAmount) : null,
          reason,
        });
      }
      if (res?.error) {
        setError(res.error);
      } else {
        closeRepair();
        load();
      }
    } finally {
      setSubmittingRepair(false);
    }
  };

  const repairActionLabel = (a: RepairAction): string => {
    switch (a) {
      case 'reopen': return 'Reopen loan';
      case 'close': return 'Force-close loan';
      case 'reverse_disbursement': return 'Reverse disbursement';
      case 'restore_disbursement': return 'Restore disbursement';
      case 'reverse_all_reps': return 'Reverse all repayments';
      case 'move_all_reps': return 'Move all repayments to another loan';
      case 'edit_disbursement_date': return 'Edit disbursement date';
      case 'edit_terms': return 'Edit loan terms';
    }
  };

  const repairActionWarning = (a: RepairAction): string => {
    switch (a) {
      case 'reopen':
        return 'Set this loan back to OPEN. Refused if the disbursement JE was already reversed.';
      case 'close':
        return 'Force-close this loan. No compensating ledger entry is posted — this only changes status.';
      case 'reverse_disbursement':
        return 'Reverses the disbursement journal entry on this loan. Refused if any live repayment is still attached — reverse or move them first.';
      case 'restore_disbursement':
        return 'Un-reverses a disbursement that was reversed in error. Brings the loan principal back onto the ledger so repayments balance against it. Refused if a live disbursement already exists.';
      case 'reverse_all_reps':
        return 'Reverses every live repayment attached to this loan and rolls each one’s deposit approval back to PENDING.';
      case 'move_all_reps':
        return 'Moves every repayment row (live and reversed) from this loan onto another loan owned by the same member. Pick the destination below.';
      case 'edit_disbursement_date':
        return 'Changes when this loan is considered to have been disbursed. Re-buckets the disbursement journal entry so the Loan/Revenue report groups it under the right month. For historical/retrospective loans where the exact date isn’t known, the last day of the borrowing month is a sensible convention.';
      case 'edit_terms':
        return 'Edit this loan’s tenure (months) and/or interest rate. The expected interest is recomputed and a correcting journal entry is posted for the delta against INTEREST_RECEIVABLE / INTEREST_INCOME, bucketed under the loan’s disbursement month. Repayment dates and amounts are not touched.';
    }
  };

  if (!memberId) return null;
  if (loading && !state) {
    return (
      <div className="card">
        <p className="text-sm text-gray-600">Loading loan state…</p>
      </div>
    );
  }
  if (!state) return null;

  const activeCount = state.summary.active_loan_count;
  const sumLoanAmt = state.loans
    .filter((l) => isActive(l.loan_status))
    .reduce((s, l) => s + l.loan_amount, 0);
  const sumPrincipalPaid = state.loans
    .filter((l) => isActive(l.loan_status))
    .reduce((s, l) => s + l.live_principal_paid, 0);
  const outstanding = sumLoanAmt - sumPrincipalPaid;
  const ledgerOutstanding = state.summary.ledger_outstanding;
  const ledgerMismatch = Math.abs(outstanding - ledgerOutstanding) > 0.01;

  return (
    <div className="card">
      <div className="flex justify-between items-start mb-3">
        <h2 className="text-lg font-bold text-blue-900">Loan State</h2>
        {activeCount > 1 && (
          <button
            onClick={openConsolidate}
            className="px-3 py-1.5 bg-amber-500 text-white rounded-lg font-semibold text-xs hover:bg-amber-600 transition-colors"
          >
            Consolidate {activeCount} loans
          </button>
        )}
      </div>

      {error && (
        <div className="px-3 py-2 mb-3 bg-red-100 border border-red-300 text-red-800 rounded text-sm">
          {error}
        </div>
      )}

      {/* Summary strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2 text-sm">
        <div className="px-3 py-2 bg-blue-50 rounded">
          <div className="text-xs text-blue-600">Active loans</div>
          <div className={`font-bold ${activeCount > 1 ? 'text-amber-700' : 'text-blue-900'}`}>
            {activeCount}
          </div>
        </div>
        <div className="px-3 py-2 bg-blue-50 rounded">
          <div className="text-xs text-blue-600">Loan amount (sum)</div>
          <div className="font-bold text-blue-900">{fmt(sumLoanAmt)}</div>
        </div>
        <div className="px-3 py-2 bg-blue-50 rounded">
          <div className="text-xs text-blue-600">Principal paid (live)</div>
          <div className="font-bold text-blue-900">{fmt(sumPrincipalPaid)}</div>
        </div>
        <div className={`px-3 py-2 rounded ${ledgerMismatch ? 'bg-amber-50' : 'bg-blue-50'}`}>
          <div className="text-xs text-blue-600">
            Outstanding {ledgerMismatch && '⚠'}
          </div>
          <div className="font-bold text-blue-900">{fmt(outstanding)}</div>
          {ledgerMismatch && (
            <div className="text-xs text-amber-700 mt-1">
              Ledger says {fmt(ledgerOutstanding)}
            </div>
          )}
        </div>
      </div>

      {/* Interest summary strip (accrual basis) */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-sm">
        <div className="px-3 py-2 bg-emerald-50 rounded">
          <div className="text-xs text-emerald-700">Interest accrued (all loans)</div>
          <div className="font-bold text-emerald-900">{fmt(state.summary.interest_expected_total)}</div>
        </div>
        <div className="px-3 py-2 bg-emerald-50 rounded">
          <div className="text-xs text-emerald-700">Interest paid (live)</div>
          <div className="font-bold text-emerald-900">{fmt(state.summary.interest_paid_total)}</div>
        </div>
        <div
          className={`px-3 py-2 rounded ${
            state.summary.interest_outstanding_total > 0.01 ? 'bg-amber-50' : 'bg-emerald-50'
          }`}
        >
          <div className="text-xs text-amber-700">Interest outstanding</div>
          <div
            className={`font-bold ${
              state.summary.interest_outstanding_total > 0.01 ? 'text-amber-900' : 'text-emerald-900'
            }`}
          >
            {fmt(state.summary.interest_outstanding_total)}
          </div>
        </div>
      </div>

      {/* Loan rows */}
      <div className="space-y-3">
        {state.loans.map((loan) => (
          <div
            key={loan.id}
            className={`border rounded-lg p-3 ${
              !loan.has_live_disbursement_je
                ? 'border-red-300 bg-red-50/40'
                : isActive(loan.loan_status)
                  ? 'border-blue-300 bg-white'
                  : 'border-gray-300 bg-gray-50'
            }`}
          >
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <div>
                <span
                  className={`text-xs font-semibold ${
                    !loan.has_live_disbursement_je ? 'text-gray-400 line-through' : 'text-gray-700'
                  }`}
                >
                  {loan.disbursement_date
                    ? new Date(loan.disbursement_date + 'T00:00:00').toLocaleDateString('en-US', {
                        month: 'long',
                        year: 'numeric',
                      })
                    : 'Undisbursed'}{' '}
                  <span className="font-mono text-gray-400 font-normal">
                    ({loan.id.slice(0, 8)})
                  </span>
                </span>
                <span
                  className={`ml-2 inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                    isActive(loan.loan_status)
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-200 text-gray-700'
                  }`}
                >
                  {loan.loan_status}
                </span>
                {!loan.has_live_disbursement_je && (
                  <span
                    className="ml-2 inline-block px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800"
                    title="The disbursement journal entry for this loan has been reversed. The loan no longer contributes to ledger balances or reports — the record remains for audit only."
                  >
                    disbursement reversed
                  </span>
                )}
                {!loan.application_id && (
                  <span className="ml-2 inline-block px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">
                    no application
                  </span>
                )}
              </div>
              <div className="text-right flex items-start gap-2">
                <div>
                  <div>
                    <strong>{fmt(loan.loan_amount)}</strong> @ {loan.percentage_interest}%
                  </div>
                  <div className="text-xs text-gray-600">
                    Disbursed: {loan.disbursement_date || '—'}
                  </div>
                </div>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setOpenMenuLoanId(openMenuLoanId === loan.id ? null : loan.id)}
                    className="ml-1 px-2 py-0.5 text-gray-500 hover:bg-gray-200 rounded text-base leading-none"
                    aria-label="Loan repair actions"
                  >
                    ⋯
                  </button>
                  {openMenuLoanId === loan.id && (
                    <div
                      className="absolute right-0 top-full mt-1 z-20 w-60 bg-white border border-gray-300 rounded-lg shadow-lg text-left text-xs"
                      onMouseLeave={() => setOpenMenuLoanId(null)}
                    >
                      {loan.loan_status === 'closed' && (
                        <button
                          onClick={() => openRepair(loan, 'reopen')}
                          className="block w-full px-3 py-2 hover:bg-blue-50 text-gray-800"
                        >
                          Reopen loan
                        </button>
                      )}
                      {isActive(loan.loan_status) && (
                        <button
                          onClick={() => openRepair(loan, 'close')}
                          className="block w-full px-3 py-2 hover:bg-blue-50 text-gray-800"
                        >
                          Force-close loan
                        </button>
                      )}
                      {loan.has_live_disbursement_je ? (
                        <button
                          onClick={() => openRepair(loan, 'reverse_disbursement')}
                          className="block w-full px-3 py-2 hover:bg-red-50 text-red-700"
                        >
                          Reverse disbursement
                        </button>
                      ) : (
                        <button
                          onClick={() => openRepair(loan, 'restore_disbursement')}
                          className="block w-full px-3 py-2 hover:bg-emerald-50 text-emerald-700"
                        >
                          Restore disbursement
                        </button>
                      )}
                      <button
                        onClick={() => openRepair(loan, 'reverse_all_reps')}
                        className="block w-full px-3 py-2 hover:bg-red-50 text-red-700"
                      >
                        Reverse all repayments
                      </button>
                      <button
                        onClick={() => openRepair(loan, 'move_all_reps')}
                        className="block w-full px-3 py-2 hover:bg-blue-50 text-gray-800"
                      >
                        Move all repayments…
                      </button>
                      <button
                        onClick={() => openRepair(loan, 'edit_disbursement_date')}
                        className="block w-full px-3 py-2 hover:bg-blue-50 text-gray-800"
                      >
                        Edit disbursement date…
                      </button>
                      <button
                        onClick={() => openRepair(loan, 'edit_terms')}
                        className="block w-full px-3 py-2 hover:bg-blue-50 text-gray-800"
                      >
                        Edit loan terms…
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-700">
              <div>
                Ledger disbursed: <strong>{fmt(loan.ledger_disbursed)}</strong>
              </div>
              <div>
                Principal paid: <strong>{fmt(loan.live_principal_paid)}</strong>
              </div>
              <div>
                Outstanding: <strong>{fmt(loan.outstanding)}</strong>
              </div>
            </div>
            <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-emerald-700">
              <div>
                Interest accrued: <strong>{fmt(loan.expected_interest)}</strong>
              </div>
              <div>
                Interest paid: <strong>{fmt(loan.live_interest_paid)}</strong>
              </div>
              <div className={loan.interest_outstanding > 0.01 ? 'text-amber-700' : ''}>
                Interest outstanding: <strong>{fmt(loan.interest_outstanding)}</strong>
              </div>
            </div>

            {loan.repayments.length > 0 && (
              <div className="mt-3 border-t pt-2">
                <div className="text-xs font-semibold text-blue-800 mb-1">
                  Repayments ({loan.repayments.length})
                </div>
                <table className="w-full text-xs">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-1">Date</th>
                      <th className="text-right py-1">Principal</th>
                      <th className="text-right py-1">Interest</th>
                      <th className="text-right py-1">Total</th>
                      <th className="text-center py-1">Live</th>
                      <th className="py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loan.repayments.map((rep) => (
                      <tr key={rep.id} className={rep.is_live ? '' : 'text-gray-400'}>
                        <td className="py-1">{rep.repayment_date || '—'}</td>
                        <td className="text-right py-1">{fmt(rep.principal_amount)}</td>
                        <td className="text-right py-1">{fmt(rep.interest_amount)}</td>
                        <td className="text-right py-1">{fmt(rep.total_amount)}</td>
                        <td className="text-center py-1">{rep.is_live ? '✓' : '↺'}</td>
                        <td className="text-right py-1 whitespace-nowrap">
                          {rep.is_live && (
                            <>
                              <button
                                onClick={() => openEditSplit(rep)}
                                className="text-blue-600 hover:underline"
                              >
                                edit split
                              </button>
                              <span className="mx-1 text-gray-300">|</span>
                              <button
                                onClick={() => openMoveRepayment(rep)}
                                className="text-blue-600 hover:underline"
                              >
                                move
                              </button>
                              <span className="mx-1 text-gray-300">|</span>
                              <button
                                onClick={() => setReverseRep(rep)}
                                className="text-red-600 hover:underline"
                              >
                                reverse
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Consolidate modal */}
      {showConsolidate && state && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto space-y-4">
            <h3 className="text-lg font-bold text-blue-900">Consolidate Loans</h3>
            <p className="text-sm text-gray-700">
              Pick the loan to keep and the amount it should have. The other selected
              loans will be closed, their disbursement journal entries reversed, and
              their repayments moved onto the kept loan. A balancing journal entry
              is posted if the new amount differs from the ledger.
            </p>

            <div className="space-y-2">
              <div className="text-sm font-semibold text-blue-900">Keep loan:</div>
              {state.loans
                .filter((l) => isActive(l.loan_status))
                .map((l) => (
                  <label
                    key={l.id}
                    className="flex items-center gap-3 p-2 border rounded hover:bg-blue-50 cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="keep"
                      value={l.id}
                      checked={keepId === l.id}
                      onChange={() => {
                        setKeepId(l.id);
                        setCloseIds(
                          state.loans
                            .filter((x) => isActive(x.loan_status) && x.id !== l.id)
                            .map((x) => x.id)
                        );
                        setNewAmount(String(l.loan_amount));
                        setNewRate(String(l.percentage_interest));
                        setNewTerm(l.number_of_instalments || '');
                      }}
                    />
                    <div className="flex-1 text-sm">
                      <div className="font-mono text-xs">{l.id.slice(0, 8)}</div>
                      <div>
                        {fmt(l.loan_amount)} @ {l.percentage_interest}% · disbursed{' '}
                        {l.disbursement_date || '—'} ·{' '}
                        {l.application_id ? 'has application' : 'no application'}
                      </div>
                    </div>
                  </label>
                ))}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">New loan amount (K)</label>
                <input
                  type="number"
                  step="0.01"
                  value={newAmount}
                  onChange={(e) => setNewAmount(e.target.value)}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">Interest rate (%)</label>
                <input
                  type="number"
                  step="0.01"
                  value={newRate}
                  onChange={(e) => setNewRate(e.target.value)}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">
                  Term (months, blank = keep)
                </label>
                <input
                  type="text"
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
              </div>
            </div>

            <div>
              <div className="text-sm font-semibold text-blue-900 mb-2">
                Loans to close ({closeIds.length}):
              </div>
              {state.loans
                .filter((l) => isActive(l.loan_status) && l.id !== keepId)
                .map((l) => (
                  <label key={l.id} className="flex items-center gap-3 p-2 text-sm">
                    <input
                      type="checkbox"
                      checked={closeIds.includes(l.id)}
                      onChange={() => toggleCloseId(l.id)}
                    />
                    <span className="font-mono text-xs">{l.id.slice(0, 8)}</span>
                    <span>
                      {fmt(l.loan_amount)} · {l.disbursement_date || '—'} ·{' '}
                      {l.repayments.length} repayments
                    </span>
                  </label>
                ))}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowConsolidate(false)}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={submitConsolidate}
                disabled={consolidating || !keepId || closeIds.length === 0}
                className="px-5 py-2 bg-amber-500 text-white rounded-lg font-semibold text-sm hover:bg-amber-600 disabled:opacity-50"
              >
                {consolidating ? 'Consolidating…' : 'Consolidate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reverse-repayment modal */}
      {reverseRep && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-4">
            <h3 className="text-lg font-bold text-red-700">Reverse Repayment</h3>
            <p className="text-sm text-gray-700">
              You are about to reverse a repayment of{' '}
              <strong>{fmt(reverseRep.principal_amount + reverseRep.interest_amount)}</strong>{' '}
              dated <strong>{reverseRep.repayment_date || '—'}</strong>.
            </p>
            <ul className="text-sm text-gray-700 list-disc pl-5 space-y-1">
              <li>The journal entry will be marked reversed (ledger is reset for this deposit).</li>
              <li>
                The linked <strong>deposit proof</strong> will be set to{' '}
                <em>rejected</em> and the <strong>declaration</strong> back to <em>pending</em>,
                so the member can edit and re-upload from the Proof of Payment (PoP) page.
              </li>
              <li>This action does not affect repayments on other loans.</li>
            </ul>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setReverseRep(null)}
                disabled={reversing}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={confirmReverseRepayment}
                disabled={reversing}
                className="px-5 py-2 bg-red-600 text-white rounded-lg font-semibold text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {reversing ? 'Reversing…' : 'Confirm Reverse'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Move-repayment modal */}
      {moveRep && state && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-4">
            <h3 className="text-lg font-bold text-blue-900">Move Repayment to a Different Loan</h3>
            <p className="text-sm text-gray-700">
              Moving a K{(moveRep.principal_amount + moveRep.interest_amount).toFixed(2)} repayment
              dated {moveRep.repayment_date || '—'}. The journal entry stays intact; only the
              loan attribution changes.
            </p>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-blue-900">Target loan</label>
              <select
                value={moveTargetLoanId}
                onChange={(e) => setMoveTargetLoanId(e.target.value)}
                className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
              >
                <option value="">Pick a loan…</option>
                {state.loans.map((l) => (
                    <option key={l.id} value={l.id} disabled={l.id === moveRep.loan_id}>
                      {l.id.slice(0, 8)} · {fmt(l.loan_amount)} ·{' '}
                      {l.disbursement_date || '—'} · {l.loan_status}
                      {l.id === moveRep.loan_id ? ' (current)' : ''}
                    </option>
                  ))}
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setMoveRep(null)}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={submitMoveRepayment}
                disabled={movingRep || !moveTargetLoanId}
                className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {movingRep ? 'Moving…' : 'Move'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit-split modal */}
      {editRep && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-4">
            <h3 className="text-lg font-bold text-blue-900">Edit Principal / Interest Split</h3>
            <p className="text-sm text-gray-700">
              Total paid stays at <strong>{fmt(editRep.total_amount)}</strong>. Adjusting the split
              posts a correcting journal entry moving the delta between LOANS_RECEIVABLE
              and INTEREST_INCOME.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">Principal (K)</label>
                <input
                  type="number"
                  step="0.01"
                  value={editPrincipal}
                  onChange={(e) => {
                    setEditPrincipal(e.target.value);
                    const p = parseFloat(e.target.value) || 0;
                    setEditInterest((editRep.total_amount - p).toFixed(2));
                  }}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">Interest (K)</label>
                <input
                  type="number"
                  step="0.01"
                  value={editInterest}
                  onChange={(e) => {
                    setEditInterest(e.target.value);
                    const i = parseFloat(e.target.value) || 0;
                    setEditPrincipal((editRep.total_amount - i).toFixed(2));
                  }}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setEditRep(null)}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={submitEditSplit}
                disabled={savingSplit}
                className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {savingSplit ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Per-loan repair modal */}
      {repairLoan && repairAction && state && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-lg mx-4 space-y-4">
            <h3 className="text-lg font-bold text-blue-900">
              {repairActionLabel(repairAction)}
            </h3>
            <div className="text-xs text-gray-500">
              Loan <span className="font-mono">{repairLoan.id.slice(0, 8)}</span> ·{' '}
              {fmt(repairLoan.loan_amount)} · {repairLoan.loan_status}
            </div>
            <p className="text-sm text-gray-700">{repairActionWarning(repairAction)}</p>

            {repairAction === 'move_all_reps' && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">
                  Destination loan
                </label>
                <select
                  value={repairTargetLoanId}
                  onChange={(e) => setRepairTargetLoanId(e.target.value)}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                >
                  <option value="">— pick a loan —</option>
                  {state.loans
                    .filter((l) => l.id !== repairLoan.id)
                    .map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.id.slice(0, 8)} · {fmt(l.loan_amount)} · {l.loan_status}
                      </option>
                    ))}
                </select>
              </div>
            )}

            {repairAction === 'edit_disbursement_date' && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-blue-900">
                  New disbursement date
                </label>
                <input
                  type="date"
                  value={repairNewDate}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setRepairNewDate(e.target.value)}
                  className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                />
                <p className="text-[11px] text-gray-500">
                  Current: <span className="font-mono">{repairLoan.disbursement_date || '—'}</span>.
                  For retrospective loans, the last day of the borrowing month is a sensible convention.
                </p>
              </div>
            )}

            {repairAction === 'edit_terms' && (() => {
              const newRateN = parseFloat(repairNewRate || '') || 0;
              const newAmountN = parseFloat(repairNewAmount || '') || repairLoan.loan_amount;
              const newExpected = newRateN > 0
                ? (newAmountN * newRateN) / 100
                : repairLoan.expected_interest;
              const oldExpected = repairLoan.expected_interest;
              const principalDelta = newAmountN - repairLoan.loan_amount;
              const interestDelta = newExpected - oldExpected;
              return (
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-blue-900">Loan amount (K)</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={repairNewAmount}
                        onChange={(e) => setRepairNewAmount(e.target.value)}
                        className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                      />
                      <p className="text-[11px] text-gray-500">
                        Current: <span className="font-mono">{fmt(repairLoan.loan_amount)}</span>
                      </p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-blue-900">Tenure (months)</label>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={repairNewTerm}
                        onChange={(e) => setRepairNewTerm(e.target.value)}
                        className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                      />
                      <p className="text-[11px] text-gray-500">
                        Current: <span className="font-mono">{repairLoan.number_of_instalments || '—'}</span>
                      </p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-semibold text-blue-900">Interest rate (%)</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={repairNewRate}
                        onChange={(e) => setRepairNewRate(e.target.value)}
                        className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
                      />
                      <p className="text-[11px] text-gray-500">
                        Current: <span className="font-mono">{repairLoan.percentage_interest}%</span>
                      </p>
                    </div>
                  </div>
                  <div className="px-3 py-2 bg-blue-50 border border-blue-200 rounded text-xs space-y-0.5">
                    <div className="flex justify-between">
                      <span className="text-blue-700">New loan amount</span>
                      <span className="font-semibold text-blue-900">{fmt(newAmountN)}</span>
                    </div>
                    <div className={`flex justify-between ${Math.abs(principalDelta) < 0.005 ? 'text-blue-700' : principalDelta > 0 ? 'text-emerald-700' : 'text-amber-700'}`}>
                      <span>Principal delta (corrective JE)</span>
                      <span className="font-bold">{principalDelta >= 0 ? '+' : ''}{fmt(principalDelta)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-blue-700">Old expected interest</span>
                      <span className="font-semibold text-blue-900">{fmt(oldExpected)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-blue-700">New expected interest</span>
                      <span className="font-semibold text-blue-900">{fmt(newExpected)}</span>
                    </div>
                    <div className={`flex justify-between pt-1 mt-1 border-t border-blue-200 ${Math.abs(interestDelta) < 0.005 ? 'text-blue-700' : interestDelta > 0 ? 'text-emerald-700' : 'text-amber-700'}`}>
                      <span>Interest accrual delta</span>
                      <span className="font-bold">{interestDelta >= 0 ? '+' : ''}{fmt(interestDelta)}</span>
                    </div>
                  </div>
                </div>
              );
            })()}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-blue-900">
                Reason (required, audit logged)
              </label>
              <textarea
                value={repairReason}
                onChange={(e) => setRepairReason(e.target.value)}
                rows={3}
                placeholder="Why are you doing this? Min 5 characters."
                className="px-3 py-2 border-2 border-blue-300 rounded text-sm"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={closeRepair}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={submitRepair}
                disabled={submittingRepair}
                className="px-5 py-2 bg-red-600 text-white rounded-lg font-semibold text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {submittingRepair ? 'Working…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
