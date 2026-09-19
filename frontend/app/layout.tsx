import './globals.css';

export const metadata = {
  title: 'AI Study System',
  description: 'Upload PDFs, generate quizzes, and track weak topics.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
