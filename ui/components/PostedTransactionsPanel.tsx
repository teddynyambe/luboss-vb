'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

type Category = 'savings' | 'social_fund' | 'admin_fund' | 'penalty';

const CATEGORY_LABEL: Record<Category, string> = {
  savings: 'Savings',
  social_fund: 'Social Fund',
  admin_fund: 'Admin Fund',
  penalty: 'Penalty',
};

interface TxLine {
  id: string;
  journal_entry_id: string;
  ledger_account_id: string;
  ledger_account_name: string;
  entry_date: string;
  category: Category;
  amount: number;
  is_live: boolean;
  je_description: string | null;
  je_source_type: string | null;
  note: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  can_act: boolean;
}

interface MonthBucket {
  month: string;        // YYYY-MM
  month_label: string;
  lines: TxLine[];
  totals: Record<Category, number>;
}

interface TxState {
  member_id: string;
  months: MonthBucket[];
  today_month: string;  // YYYY-MM
  savings_balance?: number;
}

// Subset of the Loan State payload used by the "Pay loan from savings" modal.
interface RunningLoan {
  id: string;
  loan_amount: number;
  loan_status: string | null;
  disbursement_date: string | null;
  has_live_disbursement_je: boolean;
  outstanding: number;
  interest_outstanding: number;
}

const fmt = (n: number) =>
  `${n < 0 ? '-' : ''}K${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const SOURCE_LABEL: Record<string, string> = {
  deposit_approval: 'Deposit',
  excess_contribution: 'Excess transfer',
  penalty_charge: 'Penalty charge',
  transaction_split: 'Split',
  savings_to_loan: 'Paid to loan',
};

export default function PostedTransactionsPanel({ memberId }: { memberId: string }) {
  const [state, setState] = useState<TxState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  // Action modals
  const [reverseLine, setReverseLine] = useState<TxLine | null>(null);
  const [reverseDesc, setReverseDesc] = useState('');
  const [reverseBusy, setReverseBusy] = useState(false);

  const [splitLine, setSplitLine] = useState<TxLine | null>(null);
  const [splitTarget, setSplitTarget] = useState<Category | ''>('');
  const [splitAmount, setSplitAmount] = useState('');
  const [splitDesc, setSplitDesc] = useState('');
  const [splitPenaltyTypeId, setSplitPenaltyTypeId] = useState<string>('');

  interface PenaltyTypeOption {
    id: string;
    name: string;
    fee_amount: number;
    description: string | null;
  }
  const [penaltyTypes, setPenaltyTypes] = useState<PenaltyTypeOption[]>([]);

  useEffect(() => {
    // Lazy-fetch the penalty-type catalog the first time the modal opens with
    // the penalty target — cheap, but no point loading on every panel render.
    if (splitTarget === 'penalty' && penaltyTypes.length === 0) {
      api
        .get<PenaltyTypeOption[]>('/api/chairman/reconcile/penalty-types')
        .then((res) => {
          if (res.data) setPenaltyTypes(res.data);
        });
    }
    // Clear the picked penalty type whenever the target changes off 'penalty'.
    if (splitTarget !== 'penalty' && splitPenaltyTypeId) {
      setSplitPenaltyTypeId('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [splitTarget]);
  const [splitBusy, setSplitBusy] = useState(false);

  const [moveLine, setMoveLine] = useState<TxLine | null>(null);
  const [moveTarget, setMoveTarget] = useState('');
  const [moveDesc, setMoveDesc] = useState('');
  const [moveBusy, setMoveBusy] = useState(false);

  // "Pay loan from savings" modal
  const [payOpen, setPayOpen] = useState(false);
  const [payLoans, setPayLoans] = useState<RunningLoan[] | null>(null);
  const [payLoanId, setPayLoanId] = useState('');
  const [payPrincipal, setPayPrincipal] = useState('');
  const [payInterest, setPayInterest] = useState('');
  const [payMonth, setPayMonth] = useState('');
  const [payDesc, setPayDesc] = useState('');
  const [payBusy, setPayBusy] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!memberId) {
      setState(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .get<TxState>(`/api/chairman/reconcile/transactions/${memberId}`)
      .then((res) => {
        if (res.data) setState(res.data);
        else setError(res.error || 'Failed to load transactions');
      })
      .finally(() => setLoading(false));
  }, [memberId]);

  useEffect(() => { load(); }, [load]);

  const tooShort = (s: string) => s.trim().length < 5;

  const doReverse = async () => {
    if (!reverseLine) return;
    if (tooShort(reverseDesc)) {
      setError('Description must be at least 5 characters.');
      return;
    }
    setReverseBusy(true);
    try {
      const res = await api.post(
        `/api/chairman/reconcile/transactions/${reverseLine.id}/reverse`,
        { description: reverseDesc.trim() }
      );
      if (res.error) setError(res.error);
      else { setReverseLine(null); setReverseDesc(''); load(); }
    } finally { setReverseBusy(false); }
  };

  const doSplit = async () => {
    if (!splitLine || !splitTarget) return;
    if (tooShort(splitDesc)) {
      setError('Description must be at least 5 characters.');
      return;
    }
    const amt = parseFloat(splitAmount);
    if (Number.isNaN(amt) || amt <= 0) {
      setError('Enter a positive split amount.');
      return;
    }
    setSplitBusy(true);
    try {
      if (splitTarget === 'penalty' && !splitPenaltyTypeId) {
        setError('Pick the specific penalty type before confirming the split.');
        return;
      }
      const res = await api.post(
        `/api/chairman/reconcile/transactions/${splitLine.id}/split`,
        {
          target_category: splitTarget,
          amount: amt,
          description: splitDesc.trim(),
          penalty_type_id: splitTarget === 'penalty' ? splitPenaltyTypeId : null,
        }
      );
      if (res.error) setError(res.error);
      else {
        setSplitLine(null); setSplitDesc(''); setSplitAmount(''); setSplitTarget('');
        setSplitPenaltyTypeId('');
        load();
      }
    } finally { setSplitBusy(false); }
  };

  const doMove = async () => {
    if (!moveLine || !moveTarget) return;
    if (tooShort(moveDesc)) {
      setError('Description must be at least 5 characters.');
      return;
    }
    setMoveBusy(true);
    try {
      const res = await api.post(
        `/api/chairman/reconcile/transactions/${moveLine.id}/move`,
        { target_month: moveTarget, description: moveDesc.trim() }
      );
      if (res.error) setError(res.error);
      else { setMoveLine(null); setMoveDesc(''); setMoveTarget(''); load(); }
    } finally { setMoveBusy(false); }
  };

  const openPay = async () => {
    setPayOpen(true);
    setPayLoans(null);
    setPayLoanId('');
    setPayPrincipal('');
    setPayInterest('');
    setPayMonth(state?.today_month || '');
    setPayDesc('');
    setPayError(null);
    const res = await api.get<{ loans: RunningLoan[] }>(`/api/chairman/reconcile/loan-state/${memberId}`);
    if (!res.data) {
      setPayLoans([]);
      setPayError(res.error || 'Failed to load loans');
      return;
    }
    const running = res.data.loans.filter(
      (L) => (L.loan_status === 'open' || L.loan_status === 'disbursed') && L.has_live_disbursement_je,
    );
    setPayLoans(running);
    if (running.length === 1) setPayLoanId(running[0].id);
  };

  const payLoan = payLoans?.find((L) => L.id === payLoanId) || null;
  const payP = parseFloat(payPrincipal) || 0;
  const payI = parseFloat(payInterest) || 0;
  const payTotal = payP + payI;
  const savingsBalance = state?.savings_balance ?? 0;
  const payProblem = !payLoan
    ? null
    : payP < 0 || payI < 0
    ? 'Amounts cannot be negative.'
    : payP > payLoan.outstanding + 0.005
    ? `Principal is more than the outstanding principal (${fmt(payLoan.outstanding)}).`
    : payI > payLoan.interest_outstanding + 0.005
    ? `Interest is more than the outstanding interest (${fmt(payLoan.interest_outstanding)}).`
    : payTotal > savingsBalance + 0.005
    ? `Total is more than the savings balance (${fmt(savingsBalance)}).`
    : null;

  const doPay = async () => {
    if (!payLoan || payTotal <= 0 || payProblem || tooShort(payDesc)) return;
    setPayBusy(true);
    setPayError(null);
    try {
      const res = await api.post<{ total: number; loan_closed: boolean; principal_outstanding_after: number }>(
        '/api/chairman/reconcile/savings-to-loan',
        {
          member_id: memberId,
          loan_id: payLoan.id,
          principal: payP,
          interest: payI,
          target_month: payMonth || null,
          description: payDesc.trim(),
        },
      );
      if (res.error || !res.data) setPayError(res.error || 'Failed to post the payment');
      else {
        setPayOpen(false);
        setNotice(
          `${fmt(res.data.total)} moved from savings to the loan. ` +
          (res.data.loan_closed
            ? 'The loan is now fully paid and closed.'
            : `Outstanding principal is now ${fmt(res.data.principal_outstanding_after)}.`),
        );
        load();
      }
    } finally { setPayBusy(false); }
  };

  if (!memberId) return null;
  if (loading && !state) {
    return <div className="card"><p className="text-sm text-gray-600">Loading transactions…</p></div>;
  }
  if (!state) return null;

  return (
    <div className="card">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h2 className="text-lg font-bold text-blue-900">Posted Transactions</h2>
          <p className="text-xs text-gray-600 mt-1">
            Per-month ledger lines for this member. Loan disbursements, repayments and interest
            are managed in the Loan State tab — they don&apos;t appear here.
          </p>
          <p className="text-xs text-gray-700 mt-1">
            Savings balance: <strong>{fmt(savingsBalance)}</strong>
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={openPay}
            className="text-xs px-2 py-1 bg-blue-600 text-white font-semibold rounded hover:bg-blue-700"
          >
            Pay loan from savings
          </button>
          <button
            onClick={load}
            className="text-xs px-2 py-1 border border-blue-300 rounded hover:bg-blue-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {notice && (
        <div className="px-3 py-2 mb-3 bg-green-100 border border-green-300 text-green-900 rounded text-sm flex justify-between gap-3">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-xs font-semibold">Dismiss</button>
        </div>
      )}

      {error && (
        <div className="px-3 py-2 mb-3 bg-red-100 border border-red-300 text-red-800 rounded text-sm">
          {error}
        </div>
      )}

      {state.months.length === 0 ? (
        <p className="text-sm text-gray-600 italic">No posted non-loan transactions for this member yet.</p>
      ) : (
        <div className="space-y-4">
          {state.months.map((m) => (
            <div key={m.month} className="border border-blue-200 rounded-lg">
              <div className="px-3 py-2 bg-blue-50 flex justify-between items-center">
                <div className="font-semibold text-blue-900">{m.month_label}</div>
                <div className="text-xs text-gray-700 flex gap-3">
                  {(['savings','social_fund','admin_fund','penalty'] as Category[]).map((c) => (
                    m.totals[c] !== 0 ? (
                      <span key={c}>
                        {CATEGORY_LABEL[c]}: <strong>{fmt(m.totals[c])}</strong>
                      </span>
                    ) : null
                  ))}
                </div>
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-500 bg-gray-50">
                  <tr>
                    <th className="text-left py-1.5 px-2">Date</th>
                    <th className="text-left py-1.5 px-2">Category</th>
                    <th className="text-left py-1.5 px-2">Source</th>
                    <th className="text-right py-1.5 px-2">Amount</th>
                    <th className="text-left py-1.5 px-2">Note</th>
                    <th className="text-right py-1.5 px-2 w-16">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {m.lines.map((l) => (
                    <tr key={l.id} className={l.is_live ? '' : 'text-gray-400 italic'}>
                      <td className="py-1.5 px-2 whitespace-nowrap">{l.entry_date.slice(0, 10)}</td>
                      <td className="py-1.5 px-2">{CATEGORY_LABEL[l.category]}</td>
                      <td className="py-1.5 px-2 text-xs">
                        {SOURCE_LABEL[l.je_source_type || ''] || l.je_source_type || 'manual'}
                        {!l.is_live && ' ↺'}
                      </td>
                      <td className="py-1.5 px-2 text-right font-semibold">{fmt(l.amount)}</td>
                      <td className="py-1.5 px-2 text-xs">
                        {!l.is_live && l.reversal_reason
                          ? <span title={l.reversal_reason}>Reversed: {l.reversal_reason}</span>
                          : <span title={l.je_description || ''}>{l.note || (l.je_description || '').slice(0, 60)}</span>}
                      </td>
                      <td className="py-1.5 px-2 text-right relative">
                        {l.can_act && (
                          <>
                            <button
                              onClick={() => setOpenMenu(openMenu === l.id ? null : l.id)}
                              className="px-2 py-0.5 text-base leading-none hover:bg-gray-100 rounded"
                            >
                              ⋯
                            </button>
                            {openMenu === l.id && (
                              <div
                                onMouseLeave={() => setOpenMenu(null)}
                                className="absolute right-2 top-7 z-40 bg-white border border-gray-300 rounded shadow-md text-left text-xs min-w-[140px]"
                              >
                                <button
                                  onClick={() => { setOpenMenu(null); setReverseLine(l); setReverseDesc(''); }}
                                  className="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-700"
                                >
                                  Reverse
                                </button>
                                <button
                                  onClick={() => { setOpenMenu(null); setSplitLine(l); setSplitDesc(''); setSplitAmount(String(l.amount)); setSplitTarget(''); }}
                                  className="block w-full text-left px-3 py-1.5 hover:bg-blue-50 text-blue-700"
                                >
                                  Split
                                </button>
                                <button
                                  onClick={() => { setOpenMenu(null); setMoveLine(l); setMoveDesc(''); setMoveTarget(l.entry_date.slice(0,7)); }}
                                  className="block w-full text-left px-3 py-1.5 hover:bg-blue-50 text-blue-700"
                                >
                                  Move
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {/* Pay loan from savings modal */}
      {payOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-3">
            <h3 className="text-lg font-bold text-blue-900">Pay Loan from Savings</h3>
            <p className="text-sm text-gray-700">
              Takes the amount out of this member&apos;s savings and posts it as a repayment on their
              running loan. No bank cash moves. Savings available: <strong>{fmt(savingsBalance)}</strong>.
            </p>
            {payLoans === null ? (
              <p className="text-sm text-gray-600">Loading loans…</p>
            ) : payLoans.length === 0 ? (
              <p className="text-sm italic text-amber-700 bg-amber-50 border border-amber-300 rounded px-3 py-2">
                This member has no running loan to pay.
              </p>
            ) : (
              <>
                <div>
                  <label className="block text-xs font-semibold text-blue-900">Loan</label>
                  <select value={payLoanId} onChange={(e) => setPayLoanId(e.target.value)}
                    className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm">
                    {payLoans.length > 1 && <option value="">Pick the loan…</option>}
                    {payLoans.map((L) => (
                      <option key={L.id} value={L.id}>
                        {fmt(L.loan_amount)} disbursed {L.disbursement_date || '—'} — owes {fmt(L.outstanding)} + {fmt(L.interest_outstanding)} interest
                      </option>
                    ))}
                  </select>
                </div>
                {payLoan && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-blue-900">Principal (K)</label>
                        <input type="number" inputMode="decimal" step="0.01" min="0" value={payPrincipal}
                          onChange={(e) => setPayPrincipal(e.target.value)}
                          className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm" />
                        <button type="button" onClick={() => setPayPrincipal(String(payLoan.outstanding))}
                          className="mt-1 text-[11px] text-blue-700 hover:underline">
                          Outstanding: {fmt(payLoan.outstanding)}
                        </button>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-blue-900">Interest (K)</label>
                        <input type="number" inputMode="decimal" step="0.01" min="0" value={payInterest}
                          onChange={(e) => setPayInterest(e.target.value)}
                          className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm" />
                        <button type="button" onClick={() => setPayInterest(String(payLoan.interest_outstanding))}
                          className="mt-1 text-[11px] text-blue-700 hover:underline">
                          Outstanding: {fmt(payLoan.interest_outstanding)}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-blue-900">Month</label>
                      <input type="month" value={payMonth} max={state.today_month}
                        onChange={(e) => setPayMonth(e.target.value)}
                        className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm" />
                    </div>
                    <p className="text-sm text-gray-700">
                      Total from savings: <strong>{fmt(payTotal)}</strong>
                      {payTotal > 0 && !payProblem && <> — savings after: <strong>{fmt(savingsBalance - payTotal)}</strong></>}
                    </p>
                    <label className="block text-xs font-semibold text-blue-900">Reason (required)</label>
                    <textarea
                      rows={3}
                      value={payDesc}
                      onChange={(e) => setPayDesc(e.target.value)}
                      placeholder="e.g. Member asked to settle the loan from savings (min 5 characters)"
                      className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
                    />
                  </>
                )}
              </>
            )}
            {(payProblem || payError) && (
              <p className="text-xs text-red-700">{payProblem || payError}</p>
            )}
            <div className="flex justify-end gap-3 pt-1">
              <button onClick={() => setPayOpen(false)} disabled={payBusy}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800">Cancel</button>
              <button onClick={doPay}
                disabled={payBusy || !payLoan || payTotal <= 0 || !!payProblem || tooShort(payDesc)}
                className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50">
                {payBusy ? 'Posting…' : 'Confirm Payment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reverse modal */}
      {reverseLine && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-3">
            <h3 className="text-lg font-bold text-red-700">Reverse Posted Transaction</h3>
            <p className="text-sm text-gray-700">
              Reverses <strong>{fmt(reverseLine.amount)}</strong> of {CATEGORY_LABEL[reverseLine.category]}
              {' '}on {reverseLine.entry_date.slice(0, 10)}. The ledger entry is marked reversed and the
              amount no longer counts on the member&apos;s balance. The DepositProof and Declaration
              are not changed.
            </p>
            <label className="block text-xs font-semibold text-blue-900">Reason (required)</label>
            <textarea
              rows={3}
              value={reverseDesc}
              onChange={(e) => setReverseDesc(e.target.value)}
              placeholder="Why is this being reversed? (min 5 characters)"
              className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
            />
            <div className="flex justify-end gap-3 pt-1">
              <button onClick={() => setReverseLine(null)} disabled={reverseBusy}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800">Cancel</button>
              <button onClick={doReverse} disabled={reverseBusy || tooShort(reverseDesc)}
                className="px-5 py-2 bg-red-600 text-white rounded-lg font-semibold text-sm hover:bg-red-700 disabled:opacity-50">
                {reverseBusy ? 'Reversing…' : 'Confirm Reverse'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Split modal */}
      {splitLine && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-3">
            <h3 className="text-lg font-bold text-blue-900">Split / Reallocate Transaction</h3>
            <p className="text-sm text-gray-700">
              Moves part or all of this {CATEGORY_LABEL[splitLine.category]} entry
              (<strong>{fmt(splitLine.amount)}</strong>, {splitLine.entry_date.slice(0, 10)}) to a different
              category on the same member. The ledger gets a balancing pair of entries.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-blue-900">To category</label>
                <select value={splitTarget} onChange={(e) => setSplitTarget(e.target.value as Category)}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm">
                  <option value="">Pick…</option>
                  {(['savings','social_fund','admin_fund','penalty'] as Category[])
                    // Same-category split is only useful for penalty → penalty
                    // (the "tag a specific penalty type" path). Keep it filtered
                    // out for the other categories where it'd be a no-op.
                    .filter((c) => c !== splitLine.category || c === 'penalty')
                    .map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABEL[c]}
                        {c === splitLine.category && c === 'penalty' ? ' (tag a specific type)' : ''}
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-blue-900">Amount (K)</label>
                <input type="number" inputMode="decimal" step="0.01" min="0" value={splitAmount}
                  onChange={(e) => setSplitAmount(e.target.value)}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm" />
              </div>
            </div>
            {splitTarget === 'penalty' && (
              <div>
                <label className="block text-xs font-semibold text-blue-900">
                  Penalty type <span className="text-red-600">*</span>
                </label>
                <select
                  value={splitPenaltyTypeId}
                  onChange={(e) => setSplitPenaltyTypeId(e.target.value)}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
                >
                  <option value="">Pick the specific penalty type…</option>
                  {penaltyTypes.map((pt) => (
                    <option key={pt.id} value={pt.id}>
                      {pt.name} — K{pt.fee_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-gray-500">
                  {splitLine.category === 'penalty'
                    ? 'Source is already a Penalty line — nothing moves on the ledger. The K_x is just tagged with this specific penalty type so reports can recognise income by type.'
                    : 'The split is tagged with this type and a paid PenaltyRecord is created, so reports can show penalty income by specific type.'}
                </p>
              </div>
            )}
            <label className="block text-xs font-semibold text-blue-900">Reason (required)</label>
            <textarea
              rows={3}
              value={splitDesc}
              onChange={(e) => setSplitDesc(e.target.value)}
              placeholder="Why is this being reallocated? (min 5 characters)"
              className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
            />
            <div className="flex justify-end gap-3 pt-1">
              <button onClick={() => setSplitLine(null)} disabled={splitBusy}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800">Cancel</button>
              <button onClick={doSplit}
                disabled={
                  splitBusy ||
                  !splitTarget ||
                  tooShort(splitDesc) ||
                  !splitAmount ||
                  (splitTarget === 'penalty' && !splitPenaltyTypeId)
                }
                className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50">
                {splitBusy ? 'Splitting…' : 'Confirm Split'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Move modal */}
      {moveLine && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-3">
            <h3 className="text-lg font-bold text-blue-900">Move Transaction to Another Month</h3>
            <p className="text-sm text-gray-700">
              Changes the effective month of this <strong>{fmt(moveLine.amount)}</strong>{' '}
              {CATEGORY_LABEL[moveLine.category]} entry. Future months are not allowed.
            </p>
            <label className="block text-xs font-semibold text-blue-900">Target month</label>
            <input
              type="month"
              value={moveTarget}
              max={state.today_month}
              onChange={(e) => setMoveTarget(e.target.value)}
              className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
            />
            <label className="block text-xs font-semibold text-blue-900">Reason (required)</label>
            <textarea
              rows={3}
              value={moveDesc}
              onChange={(e) => setMoveDesc(e.target.value)}
              placeholder="Why is this being moved? (min 5 characters)"
              className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm"
            />
            <div className="flex justify-end gap-3 pt-1">
              <button onClick={() => setMoveLine(null)} disabled={moveBusy}
                className="px-4 py-2 text-sm font-semibold text-gray-600 hover:text-gray-800">Cancel</button>
              <button onClick={doMove}
                disabled={moveBusy || !moveTarget || tooShort(moveDesc)}
                className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50">
                {moveBusy ? 'Moving…' : 'Confirm Move'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
