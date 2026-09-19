'use client';

import { useEffect, useMemo, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type DocumentItem = { id: number; title: string; filename: string; status: string };
type Topic = { id: number; name: string; summary: string };
type Question = { id: number; topic_id: number; question_text: string; choices: string[]; source_excerpt: string; topic_name: string };

type Result = {
  score: number;
  total_questions: number;
  accuracy: number;
  weak_topics: string[];
  recommendations: string[];
};

export default function Home() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<number | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const selectedDoc = useMemo(() => documents.find((d) => d.id === selectedDocument) || null, [documents, selectedDocument]);
  const unansweredCount = questions.filter((q) => !answers[q.id]).length;

  const loadDocuments = async () => {
    const res = await fetch(`${API}/documents`);
    setDocuments(await res.json());
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const upload = async (file: File) => {
    setBusy(true);
    setMessage('Uploading and processing...');
    try {
      const form = new FormData();
      form.append('file', file);
      const uploaded = await fetch(`${API}/documents/upload`, { method: 'POST', body: form }).then((r) => r.json());
      const processed = await fetch(`${API}/documents/${uploaded.document_id}/process`, { method: 'POST' }).then((r) => r.json());
      setMessage(`Ready: ${processed.topics_created} topics, ${processed.questions_created} questions`);
      await loadDocuments();
      setSelectedDocument(uploaded.document_id);
      await openQuiz(uploaded.document_id, false);
    } catch {
      setMessage('Upload or processing failed');
    } finally {
      setBusy(false);
    }
  };

  const openQuiz = async (documentId: number, showBusy = true) => {
    if (showBusy) {
      setBusy(true);
      setMessage('Loading quiz...');
    }
    const [t, quiz] = await Promise.all([
      fetch(`${API}/documents/${documentId}/topics`).then((r) => r.json()),
      fetch(`${API}/documents/${documentId}/quiz`).then((r) => r.json()),
    ]);
    setTopics(t);
    setQuestions(quiz.questions);
    setAttemptId(quiz.attempt_id);
    setAnswers({});
    setResult(null);
    setMessage('Quiz ready');
    if (showBusy) setBusy(false);
  };

  const submit = async () => {
    if (!attemptId) return;
    if (unansweredCount > 0) {
      setMessage('Please answer every question before submitting.');
      return;
    }
    setBusy(true);
    try {
      const payload = { answers: questions.map((q) => ({ question_id: q.id, selected_answer: answers[q.id] })) };
      const out = (await fetch(`${API}/quizzes/${attemptId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then((r) => r.json())) as Result;
      setResult(out);
      setMessage('Scored successfully');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen p-4 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="rounded-3xl bg-slate-900 p-6 shadow-xl">
          <h1 className="text-3xl font-bold">AI Study System</h1>
          <p className="mt-2 text-slate-300">Upload a PDF, generate topic-based quizzes, and review weak areas.</p>
          <input disabled={busy} className="mt-4 block w-full rounded-lg bg-white p-3" type="file" accept="application/pdf" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <p className="mt-2 text-sm text-slate-400">{message}</p>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-3xl bg-slate-900 p-6">
            <h2 className="text-xl font-semibold">Documents</h2>
            <div className="mt-4 space-y-3">
              {documents.map((doc) => (
                <button key={doc.id} onClick={() => { setSelectedDocument(doc.id); void openQuiz(doc.id); }} className={`w-full rounded-2xl border p-4 text-left transition ${selectedDoc?.id === doc.id ? 'border-cyan-400 bg-slate-800' : 'border-slate-700 hover:border-slate-500'}`}>
                  <div className="font-medium">{doc.title}</div>
                  <div className="text-sm text-slate-400">{doc.filename} · {doc.status}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-3xl bg-slate-900 p-6">
            <h2 className="text-xl font-semibold">Topics</h2>
            <div className="mt-4 space-y-3">
              {topics.map((topic) => (
                <div key={topic.id} className="rounded-2xl border border-slate-700 p-4">
                  <div className="font-medium">{topic.name}</div>
                  <div className="text-sm text-slate-400">{topic.summary}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {questions.length > 0 && (
          <section className="rounded-3xl bg-slate-900 p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-xl font-semibold">Quiz</h2>
              <button onClick={submit} disabled={busy} className="rounded-xl bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-60">Submit</button>
            </div>
            <p className="mt-2 text-sm text-slate-400">{unansweredCount > 0 ? `${unansweredCount} unanswered questions` : 'All questions answered'}</p>
            <div className="mt-6 space-y-6">
              {questions.map((q, index) => (
                <div key={q.id} className="rounded-2xl border border-slate-700 p-4">
                  <div className="text-sm text-cyan-300">{q.topic_name}</div>
                  <div className="mt-1 font-medium">{index + 1}. {q.question_text}</div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {q.choices.map((choice, idx) => {
                      const letter = ['A', 'B', 'C', 'D'][idx];
                      return (
                        <label key={letter} className={`cursor-pointer rounded-xl border p-3 ${answers[q.id] === letter ? 'border-cyan-400 bg-slate-800' : 'border-slate-700'}`}>
                          <input className="mr-2" type="radio" name={`q-${q.id}`} value={letter} checked={answers[q.id] === letter} onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: letter }))} />
                          <span className="text-sm">{letter}. {choice}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {result && (
          <section className="rounded-3xl bg-emerald-950 p-6">
            <h2 className="text-xl font-semibold">Results</h2>
            <p className="mt-2">Score: {result.score} / {result.total_questions} ({Math.round(result.accuracy * 100)}%)</p>
            <p className="mt-2 font-medium">Weak topics: {result.weak_topics?.length ? result.weak_topics.join(', ') : 'None'}</p>
            <div className="mt-4 space-y-2 text-sm text-emerald-100">
              {result.recommendations?.map((r, i) => <div key={i}>• {r}</div>)}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
