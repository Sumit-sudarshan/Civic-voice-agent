import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, TrendingUp } from 'lucide-react';
import { fetchEvalReport, runLiveEval, fetchEvalTrends } from '../api/client';

// Dependency-free inline-SVG sparkline for a metric's recent run history.
function Sparkline({ points, goal }) {
  const vals = points.map((p) => p.value).filter((v) => v != null);
  if (vals.length < 2) {
    return <span className="text-[11px] text-gray-400">need ≥2 runs</span>;
  }
  const w = 120, h = 28, pad = 3;
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i) => pad + (i * (w - 2 * pad)) / (vals.length - 1);
  const y = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const d = vals.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');

  const first = vals[0], last = vals[vals.length - 1];
  const delta = +(last - first).toFixed(1);
  // "goal up" means higher is better; color the net change by whether it helped.
  const good = goal === 'down' ? delta <= 0 : delta >= 0;
  const stroke = delta === 0 ? '#9ca3af' : good ? '#059669' : '#dc2626';

  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(vals.length - 1)} cy={y(last)} r="2.2" fill={stroke} />
    </svg>
  );
}

function TrendRow({ meta, points }) {
  const label = meta?.label || 'metric';
  const unit = meta?.unit ?? '%';
  const goal = meta?.goal || 'up';
  const vals = points.map((p) => p.value).filter((v) => v != null);
  const last = vals[vals.length - 1];
  const prev = vals.length >= 2 ? vals[vals.length - 2] : null;
  const delta = prev != null ? +(last - prev).toFixed(1) : null;
  const deltaGood = delta == null ? null : (goal === 'down' ? delta <= 0 : delta >= 0);

  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-gray-100 last:border-0">
      <div className="min-w-0">
        <div className="text-sm text-black">{label}</div>
        <div className="text-[11px] text-gray-400">{points.length} run(s){goal === 'down' ? ' · lower is better' : ' · higher is better'}</div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <Sparkline points={points} goal={goal} />
        <div className="text-right w-24">
          <div className="text-sm font-bold text-black">{last != null ? `${last}${unit}` : '—'}</div>
          {delta != null && delta !== 0 && (
            <div className={`text-[11px] font-semibold ${deltaGood ? 'text-emerald-600' : 'text-red-600'}`}>
              {delta > 0 ? '+' : ''}{delta}{unit} vs prev
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function scoreColor(value) {
  if (value === null || value === undefined) return 'text-gray-400';
  if (value >= 85) return 'text-emerald-600';
  if (value >= 65) return 'text-amber-600';
  return 'text-red-600';
}

function Pct({ value }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
  return <span className={scoreColor(value)}>{value.toFixed(1)}%</span>;
}

function Delta({ value }) {
  if (value === null || value === undefined) return null;
  if (value === 0) return <span className="text-gray-500 text-xs font-semibold ml-2">(±0 vs baseline)</span>;
  const positive = value > 0;
  return (
    <span className={`text-xs font-semibold ml-2 ${positive ? 'text-emerald-600' : 'text-red-600'}`}>
      ({positive ? '+' : ''}{value.toFixed(1)} vs baseline)
    </span>
  );
}

// ── Section wrapper: number badge, title, big score, then plain-English explanation ──
function Section({ number, title, score, explains, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">
          {number}
        </span>
        <h3 className="text-sm font-bold text-black">{title}</h3>
      </div>
      <div className="text-3xl font-black mb-3">{score}</div>
      {children}
      <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{explains}</p>
    </div>
  );
}

// Per-label F1 chips — surfaces the breakdown run_eval.py already computes
// (which categories/labels get confused), not just the headline accuracy.
function PerLabelF1({ data }) {
  if (!data?.per_label) return null;
  const entries = Object.entries(data.per_label).filter(([, v]) => v.support > 0);
  if (!entries.length) return null;
  return (
    <div className="mt-2">
      {data.macro_f1 != null && (
        <div className="text-xs text-gray-500 mb-1">Macro F1: <span className="font-semibold text-black">{data.macro_f1}</span></div>
      )}
      <div className="flex flex-wrap gap-1">
        {entries.map(([lbl, v]) => (
          <span key={lbl} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 capitalize">
            {lbl.replace(/_/g, ' ')} <span className="font-semibold text-black">F1 {v.f1}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// One judge-vs-human agreement line for a field.
function AgreementRow({ label, a }) {
  if (!a || !a.n) return null;
  return (
    <div className="flex justify-between items-baseline text-sm py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-black capitalize">{label.replace(/_/g, ' ')}</span>
      <span className={`font-semibold ${scoreColor(a.pct_within_1)}`}>
        {a.pct_within_1}% within 1pt
        <span className="text-gray-500 font-normal text-xs"> · MAE {a.mae} · H{a.human_mean}/J{a.judge_mean} (n={a.n})</span>
      </span>
    </div>
  );
}

function RubricRow({ label, stat }) {
  if (!stat || stat.n === 0) {
    return (
      <div className="flex justify-between text-sm py-1.5">
        <span className="text-black">{label.replace(/_/g, ' ')}</span>
        <span className="text-gray-400">Not yet reviewed</span>
      </div>
    );
  }
  return (
    <div className="flex justify-between items-baseline text-sm py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-black capitalize">{label.replace(/_/g, ' ')}</span>
      <span className={`font-semibold ${scoreColor(stat.mean * 20)}`}>
        {stat.mean}/5 <span className="text-gray-500 font-normal text-xs">· {stat.pct_ge_4}% ≥4 (n={stat.n})</span>
      </span>
    </div>
  );
}

// ── Per-case live example card ──
function ExampleCard({ ex }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <p className="text-sm text-black mb-2">"{ex.raw_text}"</p>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <span className={ex.gatekeeper.correct ? 'text-emerald-600 font-semibold' : 'text-red-600 font-semibold'}>
          Gatekeeper: {ex.gatekeeper.predicted_label} {ex.gatekeeper.correct ? '✓' : '✗'}
        </span>
        {ex.classification && (
          <span className={ex.classification.correct ? 'text-emerald-600 font-semibold' : 'text-red-600 font-semibold'}>
            Category: {ex.classification.predicted} (expected {ex.classification.expected}) {ex.classification.correct ? '✓' : '✗'}
          </span>
        )}
        {ex.urgency && (
          <span className={ex.urgency.exact ? 'text-emerald-600 font-semibold' : ex.urgency.within_one ? 'text-amber-600 font-semibold' : 'text-red-600 font-semibold'}>
            Urgency: {ex.urgency.predicted} (expected {ex.urgency.expected}) {ex.urgency.exact ? '✓' : ex.urgency.within_one ? '~' : '✗'}
          </span>
        )}
      </div>
      {ex.extraction && (
        <div className="mt-2 pt-2 border-t border-gray-100 text-xs text-black space-y-0.5">
          <div><span className="text-gray-500">Location:</span> {ex.extraction.location}</div>
          <div><span className="text-gray-500">Summary:</span> {ex.extraction.issue_summary}</div>
          <div><span className="text-gray-500">Affected parties:</span> {ex.extraction.affected_parties}</div>
          <div><span className="text-gray-500">Requested action:</span> {ex.extraction.ask}</div>
        </div>
      )}
    </div>
  );
}

export default function EvalConsole() {
  const [baseline, setBaseline] = useState(null);
  const [baselineError, setBaselineError] = useState('');
  const [live, setLive] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState('');

  const [trends, setTrends] = useState(null);

  const loadBaseline = useCallback(() => {
    fetchEvalReport().then(setBaseline).catch(e => setBaselineError(e.message));
    fetchEvalTrends(20).then(setTrends).catch(() => {});
  }, []);

  useEffect(() => { loadBaseline(); }, [loadBaseline]);

  const handleEvaluate = () => {
    setLiveLoading(true);
    setLiveError('');
    runLiveEval()
      .then(setLive)
      .catch(e => setLiveError(e.message))
      .finally(() => setLiveLoading(false));
  };

  const exp = baseline?.explanations || {};
  const gk = baseline?.eval?.gatekeeper;
  const cl = baseline?.eval?.classification;
  const ug = baseline?.eval?.urgency;
  const dd = baseline?.eval?.dedup;

  return (
    <div className="min-h-screen bg-[#fafafa] text-black font-sans">
      <div className="max-w-6xl mx-auto px-6 py-8">

        {/* ---------------- Header ---------------- */}
        <div className="flex items-center justify-between flex-wrap gap-4 mb-1">
          <div>
            <h1 className="text-2xl font-bold text-black">Evaluation Console</h1>
            <p className="text-sm text-gray-600 mt-1">
              Measured accuracy and quality across the complaint-handling pipeline, with an explanation for each metric.
            </p>
          </div>
          <button
            onClick={handleEvaluate}
            disabled={liveLoading}
            className="flex items-center gap-2 bg-[#0e75c6] hover:bg-[#054483] disabled:bg-gray-300 disabled:text-gray-500 text-white font-semibold px-5 py-2.5 rounded-lg transition-colors shrink-0"
          >
            {liveLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            {liveLoading ? 'Running live check…' : 'Evaluate Now'}
          </button>
        </div>

        {baselineError && (
          <div className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            Failed to load baseline: {baselineError}
          </div>
        )}

        {/* ---------------- Baseline meta line ---------------- */}
        {baseline?.eval && (
          <div className="mt-4 mb-5 text-xs text-gray-600 bg-white border border-gray-200 rounded-lg px-4 py-2.5 inline-block">
            Baseline run: model <span className="font-semibold text-black">{baseline.eval_model}</span>
            {' · '}suite <span className="font-semibold text-black">{baseline.eval_suite}</span>
            {' · '}<span className="font-semibold text-black">{baseline.eval_total_cases}</span> cases
            {' · '}{baseline.eval_timestamp && new Date(baseline.eval_timestamp).toLocaleString()}
            {' · '}file <span className="font-mono">{baseline.eval_report_file}</span>
          </div>
        )}

        {/* ---------------- Trends (observability over runs) ---------------- */}
        {trends?.trends && Object.keys(trends.trends).length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm mb-5">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="w-4 h-4 text-[#0e75c6]" />
              <h3 className="text-sm font-bold text-black">Metric Trends — last {20} runs</h3>
            </div>
            <p className="text-xs text-gray-600 mb-3">
              How each metric moves as you iterate on the prompt/model. Every eval run appends a point here
              (stored separately from the app data, so history survives DB resets). Green = moved the right way.
            </p>
            <div>
              {Object.entries(trends.trends).map(([metric, points]) => (
                <TrendRow key={metric} meta={trends.metrics_meta?.[metric]} points={points} />
              ))}
            </div>
          </div>
        )}

        {/* ---------------- Section 1-4: pipeline accuracy ---------------- */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Section number={1} title={exp.gatekeeper?.label || 'Gatekeeper accuracy'} score={<Pct value={gk?.accuracy_pct} />} explains={exp.gatekeeper?.explains}>
            <div className="text-xs text-gray-500">{gk ? `${gk.correct}/${gk.total} correct` : 'No data available'}</div>
            <PerLabelF1 data={baseline?.eval?.gatekeeper_multiclass} />
          </Section>

          <Section number={2} title={exp.classification?.label || 'Category accuracy'} score={<Pct value={cl?.accuracy_pct} />} explains={exp.classification?.explains}>
            <div className="text-xs text-gray-500">{cl ? `${cl.correct}/${cl.total} correct` : 'No data available'}</div>
            {baseline?.eval?.classification_complaint && (
              <div className="mt-2 text-[11px] text-gray-500 font-semibold uppercase tracking-wide">Complaints</div>
            )}
            <PerLabelF1 data={baseline?.eval?.classification_complaint} />
            {baseline?.eval?.classification_suggestion && (
              <div className="mt-2 text-[11px] text-gray-500 font-semibold uppercase tracking-wide">Suggestions</div>
            )}
            <PerLabelF1 data={baseline?.eval?.classification_suggestion} />
          </Section>

          <Section number={3} title={exp.urgency_exact?.label || 'Urgency scoring'} score={<Pct value={ug?.exact_match_pct} />} explains={exp.urgency_exact?.explains}>
            <div className="text-xs text-gray-500">
              exact match shown above · within-one-level: <Pct value={ug?.within_one_pct} />
            </div>
          </Section>

          <Section number={4} title={exp.dedup?.label || 'Duplicate detection'} score={dd ? `Precision ${dd.precision?.toFixed(2)} / Recall ${dd.recall?.toFixed(2)}` : '—'} explains={exp.dedup?.explains}>
            <div className="text-xs text-gray-500">
              {dd
                ? `Precision: of pairs flagged as duplicates, the share that were correct. Recall: of true duplicate pairs, the share that were found. (${dd.tp} correct, ${dd.fp} false positives, ${dd.fn} missed)`
                : 'No data available'}
            </div>
          </Section>
        </div>

        {/* ---------------- Section 5-6: human-scored quality ---------------- */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">5</span>
              <h3 className="text-sm font-bold text-black">{exp.extraction?.label || 'Extraction quality'}</h3>
            </div>
            {baseline?.extraction ? (
              <div>{Object.entries(baseline.extraction).map(([field, stat]) => <RubricRow key={field} label={field} stat={stat} />)}</div>
            ) : <div className="text-sm text-gray-400 mb-3">Not yet reviewed</div>}
            <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{exp.extraction?.explains}</p>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">6</span>
              <h3 className="text-sm font-bold text-black">{exp.actionability?.label || 'Dashboard actionability'}</h3>
            </div>
            {baseline?.actionability ? (
              <div>
                {Object.entries(baseline.actionability.means).map(([dim, mean]) => (
                  <div key={dim} className="flex justify-between items-baseline text-sm py-1.5 border-b border-gray-100 last:border-0">
                    <span className="text-black capitalize">{dim.replace(/_/g, ' ')}</span>
                    <span className={`font-semibold ${scoreColor(mean * 20)}`}>{mean}/5</span>
                  </div>
                ))}
                <div className="text-xs text-gray-500 mt-2">scorer: {baseline.actionability.scorer} · n={baseline.actionability.n_states} dashboard state(s)</div>
              </div>
            ) : <div className="text-sm text-gray-400 mb-3">Not yet reviewed</div>}
            <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{exp.actionability?.explains}</p>
          </div>
        </div>

        {/* ---------------- Section 7: multilingual support ---------------- */}
        {baseline?.multilingual && (
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm mt-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">7</span>
              <h3 className="text-sm font-bold text-black">{exp.multilingual?.label || 'Multilingual support'}</h3>
            </div>
            <div className="text-xs text-gray-600 mb-3">
              model <span className="font-semibold text-black">{baseline.multilingual_model}</span>
              {' · '}<span className="font-semibold text-black">{baseline.multilingual_total_cases}</span> cases (5 Hindi + 5 Marathi + 5 Hinglish)
              {' · '}{baseline.multilingual_timestamp && new Date(baseline.multilingual_timestamp).toLocaleString()}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 text-xs uppercase tracking-wide border-b border-gray-200">
                    <th className="py-1.5 pr-4 font-semibold">Language</th>
                    <th className="py-1.5 pr-4 font-semibold">Gatekeeper</th>
                    <th className="py-1.5 pr-4 font-semibold">Category</th>
                    <th className="py-1.5 pr-4 font-semibold">Urgency exact</th>
                    <th className="py-1.5 font-semibold">n</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-gray-100 font-semibold">
                    <td className="py-1.5 pr-4 text-black">All combined</td>
                    <td className="py-1.5 pr-4"><Pct value={baseline.multilingual.gatekeeper?.accuracy_pct} /></td>
                    <td className="py-1.5 pr-4"><Pct value={baseline.multilingual.classification?.accuracy_pct} /></td>
                    <td className="py-1.5 pr-4"><Pct value={baseline.multilingual.urgency?.exact_match_pct} /></td>
                    <td className="py-1.5 text-gray-500">{baseline.multilingual_total_cases}</td>
                  </tr>
                  {['hindi', 'marathi', 'hinglish'].map(lang => {
                    const row = baseline.multilingual.language_breakdown?.[lang];
                    return (
                      <tr key={lang} className="border-b border-gray-100 last:border-0">
                        <td className="py-1.5 pr-4 text-black capitalize">{lang}</td>
                        <td className="py-1.5 pr-4"><Pct value={row?.gatekeeper_pct} /></td>
                        <td className="py-1.5 pr-4"><Pct value={row?.category_pct} /></td>
                        <td className="py-1.5 pr-4"><Pct value={row?.urgency_exact_pct} /></td>
                        <td className="py-1.5 text-gray-500">{row?.n ?? '—'}</td>
                      </tr>
                    );
                  })}
                  {baseline.eval && (
                    <tr className="text-gray-500 italic">
                      <td className="py-1.5 pr-4">English baseline (for comparison)</td>
                      <td className="py-1.5 pr-4"><Pct value={baseline.eval.gatekeeper?.accuracy_pct} /></td>
                      <td className="py-1.5 pr-4"><Pct value={baseline.eval.classification?.accuracy_pct} /></td>
                      <td className="py-1.5 pr-4"><Pct value={baseline.eval.urgency?.exact_match_pct} /></td>
                      <td className="py-1.5 text-gray-500">{baseline.eval_total_cases}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{exp.multilingual?.explains}</p>
          </div>
        )}

        {/* ---------------- Section 8: LLM-judge extraction quality (validated) ---------------- */}
        {baseline?.llm_judge && (
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm mt-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">8</span>
              <h3 className="text-sm font-bold text-black">{exp.llm_judge?.label || 'Extraction quality (LLM-judge)'}</h3>
            </div>
            <div className="text-xs text-gray-600 mb-3">
              model <span className="font-semibold text-black">{baseline.llm_judge.model}</span>
              {' · '}<span className="font-semibold text-black">{baseline.llm_judge.n}</span> cases judged
              {baseline.llm_judge_report_file && <> · file <span className="font-mono">{baseline.llm_judge_report_file}</span></>}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
              <div>
                <div className="text-[11px] text-gray-500 font-semibold uppercase tracking-wide mb-1">Judge scores (1-5)</div>
                {Object.entries(baseline.llm_judge.summary || {}).map(([field, stat]) => <RubricRow key={field} label={field} stat={stat} />)}
                {baseline.llm_judge.verbatim_copy && (
                  <div className="text-xs text-gray-500 mt-2">
                    Verbatim-copy check: mean overlap <span className="font-semibold text-black">{baseline.llm_judge.verbatim_copy.mean_copy_ratio}</span>
                    {' · '}{baseline.llm_judge.verbatim_copy.pct_flagged}% flagged as copied (≥{baseline.llm_judge.verbatim_copy.threshold})
                  </div>
                )}
              </div>

              <div>
                <div className="text-[11px] text-gray-500 font-semibold uppercase tracking-wide mb-1">
                  Validation vs. human scores {baseline.llm_judge_validation?.overall?.n ? `(n=${baseline.llm_judge_validation.overall.n})` : ''}
                </div>
                {baseline.llm_judge_validation ? (
                  <>
                    {Object.entries(baseline.llm_judge_validation.agreement || {}).map(([field, a]) => <AgreementRow key={field} label={field} a={a} />)}
                    {baseline.llm_judge_validation.overall?.n > 0 && (
                      <div className="flex justify-between items-baseline text-sm py-1.5 mt-1 font-semibold">
                        <span className="text-black">Overall</span>
                        <span className={scoreColor(baseline.llm_judge_validation.overall.pct_within_1)}>
                          {baseline.llm_judge_validation.overall.pct_within_1}% within 1pt · MAE {baseline.llm_judge_validation.overall.mae}
                        </span>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-sm text-gray-400">Run <span className="font-mono text-xs">score_extraction_llm.py --validate</span> to populate.</div>
                )}
              </div>
            </div>

            <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{exp.llm_judge?.explains}</p>
          </div>
        )}

        {/* ---------------- Section 9: Task-based summary actionability ---------------- */}
        {baseline?.summary_actionability && (
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm mt-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-5 h-5 rounded-full bg-gray-700 text-white text-[11px] font-bold flex items-center justify-center shrink-0">9</span>
              <h3 className="text-sm font-bold text-black">{exp.summary_actionability?.label || 'Summary actionability'}</h3>
            </div>
            <div className="text-xs text-gray-600 mb-3">
              model <span className="font-semibold text-black">{baseline.summary_actionability.model}</span>
              {' · '}<span className="font-semibold text-black">{baseline.summary_actionability.scenarios_run}</span> briefing(s)
              {' · '}{baseline.summary_actionability.issues_per_scenario} issues each
            </div>

            <div className="text-3xl font-black mb-2">
              <Pct value={baseline.summary_actionability.reader_accuracy_overall_pct} />
              <span className="text-sm font-medium text-gray-500 ml-2">reader accuracy from summary alone</span>
            </div>

            {baseline.summary_actionability.reader_accuracy_per_field_pct && (
              <div>
                {Object.entries(baseline.summary_actionability.reader_accuracy_per_field_pct).map(([field, pct]) => (
                  <div key={field} className="flex justify-between items-baseline text-sm py-1.5 border-b border-gray-100 last:border-0">
                    <span className="text-black capitalize">{field.replace(/_/g, ' ')}</span>
                    <span className="font-semibold"><Pct value={pct} /></span>
                  </div>
                ))}
              </div>
            )}
            {baseline.summary_actionability.verdict_direction_mismatch_pct != null && (
              <div className="text-xs text-gray-500 mt-2">
                Verdict direction mismatch: <span className="font-semibold text-black">{baseline.summary_actionability.verdict_direction_mismatch_pct}%</span> (the one LLM-written line pointing the wrong way — escalate/quiet/normal)
              </div>
            )}

            <p className="text-sm text-black leading-relaxed mt-3 pt-3 border-t border-gray-100">{exp.summary_actionability?.explains}</p>
          </div>
        )}

        {/* ---------------- Live check ---------------- */}
        {(live || liveLoading || liveError) && (
          <div className="mt-8">
            <h2 className="text-lg font-bold text-black mb-1">Live Check — Quick Sample Run</h2>
            <p className="text-xs text-gray-600 mb-4">
              {live && `${live.sample_size} cases · ${live.elapsed_seconds}s · model ${live.model} · run ${new Date(live.timestamp).toLocaleTimeString()}. Based on a small sample — treat the differences below as directional rather than statistically precise.`}
            </p>

            {liveError && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                Live check failed: {liveError}
              </div>
            )}

            {live && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Section number={1} title="Gatekeeper (Live)" score={<Pct value={live.metrics.gatekeeper.accuracy_pct} />} explains={exp.gatekeeper?.explains}>
                    <Delta value={live.deltas.gatekeeper} />
                  </Section>
                  <Section number={2} title="Category (Live)" score={<Pct value={live.metrics.classification.accuracy_pct} />} explains={exp.classification?.explains}>
                    <Delta value={live.deltas.classification} />
                  </Section>
                  <Section number={3} title="Urgency Exact-Match (Live)" score={<Pct value={live.metrics.urgency_exact.accuracy_pct} />} explains={exp.urgency_exact?.explains}>
                    <div className="text-xs text-gray-500">Within one level: <Pct value={live.metrics.urgency_within_one.accuracy_pct} /></div>
                    <Delta value={live.deltas.urgency_exact} />
                  </Section>
                  <Section number={4} title="Duplicate Detection (Live)" score={
                    live.dedup_smoke_check && !live.dedup_smoke_check.error
                      ? `Similarity ${live.dedup_smoke_check.similarity}`
                      : '—'
                  } explains={exp.dedup?.explains}>
                    {live.dedup_smoke_check && !live.dedup_smoke_check.error && (
                      <div className={live.dedup_smoke_check.correct ? 'text-emerald-600 text-xs font-semibold' : 'text-red-600 text-xs font-semibold'}>
                        {live.dedup_smoke_check.correct ? '✓ correctly matched as duplicate' : '✗ missed the known duplicate'}
                      </div>
                    )}
                  </Section>
                </div>

                <div className="mt-6">
                  <h3 className="text-sm font-bold text-black mb-2">
                    Individual Case Results <span className="font-normal text-gray-500">(for manual review — extraction quality is not scored automatically)</span>
                  </h3>
                  <div className="space-y-2">
                    {live.examples.map(ex => <ExampleCard key={ex.id} ex={ex} />)}
                  </div>
                </div>

                {live.live_summary_sample && (
                  <div className="mt-6">
                    <h3 className="text-sm font-bold text-black mb-2">
                      Sample Summary Output <span className="font-normal text-gray-500">(for illustration only — actionability is reviewed manually, not scored automatically)</span>
                    </h3>
                    <pre className="bg-white border border-gray-200 rounded-lg p-4 text-xs text-black whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto shadow-sm">
                      {live.live_summary_sample}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
