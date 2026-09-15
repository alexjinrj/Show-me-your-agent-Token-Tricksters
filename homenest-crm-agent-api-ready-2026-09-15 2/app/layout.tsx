import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'HomeNest CRM Agent · Service Recovery Workspace',
  icons: { icon: '/favicon.svg' },
  description:
    'Explainable customer scoring, complaint triage, cross-functional investigation, resolution comparison and human approval.',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
