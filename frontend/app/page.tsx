'use client';

import { useEffect, useMemo, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type DocumentItem = { id: number; title: string; filename: string; status: string };
type Topic = { id: number; name: string; summary: string };
type Question = { id: number; topic_id: number; question_text: string; choices: string[]; source_excerpt: string; topic_name: string };

export default function Home() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<number | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [attemptId, setAttemptId] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const selectedDoc = useMemo(() => documents.find((d) => d.id === selectedDocument) || null, [documents, selectedDocument]);

  const loadDocuments = async () => {
    const res = await fetch(`${API}/documents`);
    setDocuments(await res.json());
  };

  useEffect(() => { loadDocuments(); }, []);

  const upload = async (file: File) => {
    setBusy(true); setMessage('Uploading...');
    const form = new FormData(); form.append('file', file);
    const uploaded = await fetch(`${API}/documents/upload`, { method: 'POST', body: form }).then((r) => r.json());
    await fetch(`${API}/documents/${uploaded.document_id}/process`, { method: 'POST' });
    setMessage('Processed successfully');
    await loadDocuments();
    setSelectedDocument(uploaded.document_id);
    setBusy(false);
  };

  const openQuiz = async (documentId: number) => {
    setBusy(true); setMessage('Loading quiz...');
    const t = await fetch(`${API}/documents/${documentId}/topics`).then((r) => r.json());
    const quiz = await fetch(`${API}/documents/${documentId}/quiz`).then((r) => r.json());
    setTopics(t); setQuestions(quiz.questions); setAttemptId(quiz.attempt_id); setAnswers({}); setResult(null);
    setBusy(false); setMessage('Quiz ready');
  };

  const submit = async () => {
    if (!attemptId) return;
    setBusy(true);
    const payload = { answers: questions.map((q) => ({ question_id: q.id, selected_answer: answers[q.id] || 'A' })) };
    const out = await fetch(`${API}/quizzes/${attemptId}/submit`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then((r) => r.json());
    setResult(out); setBusy(false);
  };

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="rounded-2xl bg-slate-900 p-6 shadow-xl">
          <h1 className="text-3xl font-bold">AI Study System</h1>
          <p className="mt-2 text-slate-300">Upload a PDF, generate topic-based quizzes, and review weak areas.</p>
          <input disabled={busy} className="mt-4 block w-full rounded-lg bg-white p-3" type="file" accept="application/pdf" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <p className="mt-2 text-sm text-slate-400">{message}</p>
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl bg-slate-900 p-6">
            <h2 className="text-xl font-semibold">Documents</h2>
            <div className="mt-4 space-y-3">
              {documents.map((doc) => (
                <button key={doc.id} onClick={() => { setSelectedDocument(doc.id); openQuiz(doc.id); }} className={`w-full rounded-xl border p-4 text-left ${selectedDoc?.id === doc.id ? 'border-cyan-400' : 'border-slate-700'}`}>
                  <div className="font-medium">{doc.title}</div>
                  <div className="text-sm text-slate-400">