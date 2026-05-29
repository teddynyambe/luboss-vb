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
}

const fmt = (n: number) =>
  `${n < 0 ? '-' : ''}K${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const SOURCE_LABEL: Record<string, string> = {
  deposit_approval: 'Deposit',
  excess_contribution: 'Excess transfer',
  penalty_charge: 'Penalty charge',
  transaction_split: 'Split',
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
  const [splitBusy, setSplitBusy] = useState(false);

  const [moveLine, setMoveLine] = useState<TxLine | null>(null);
  const [moveTarget, setMoveTarget] = useState('');
  const [moveDesc, setMoveDesc] = useState('');
  const [moveBusy, setMoveBusy] = useState(false);

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
      const res = await api.post(
        `/api/chairman/reconcile/transactions/${splitLine.id}/split`,
        {
          target_category: splitTarget,
          amount: amt,
          description: splitDesc.trim(),
        }
      );
      if (res.error) setError(res.error);
      else {
        setSplitLine(null); setSplitDesc(''); setSplitAmount(''); setSplitTarget('');
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
        </div>
        <button
          onClick={load}
          className="text-xs px-2 py-1 border border-blue-300 rounded hover:bg-blue-50"
        >
          Refresh
        </button>
      </div>

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
            <div key={m.month} className="border border-blue-200 rounded-lg overflow-hidden">
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
                          : (l.je_description || '').slice(0, 60)}
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
                                className="absolute right-2 top-7 z-10 bg-white border border-gray-300 rounded shadow-md text-left text-xs min-w-[140px]"
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
                    .filter((c) => c !== splitLine.category)
                    .map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-blue-900">Amount (K)</label>
                <input type="number" step="0.01" min="0" value={splitAmount}
                  onChange={(e) => setSplitAmount(e.target.value)}
                  className="w-full px-3 py-2 border-2 border-blue-300 rounded text-sm" />
              </div>
            </div>
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
                disabled={splitBusy || !splitTarget || tooShort(splitDesc) || !splitAmount}
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
