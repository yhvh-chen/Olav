import type { Metadata } from 'next';
import { ThemeProvider } from 'next-themes';
import { AuthGuard } from '@/components/auth-guard';
import './globals.css';

export const metadata: Metadata = {
  title: 'OLAV - Enterprise Network Operations',
  description: 'AI-Powered Network Diagnostics and Operations Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <AuthGuard>
            {children}
          </AuthGuard>
        </ThemeProvider>
      </body>
    </html>
  );
}
