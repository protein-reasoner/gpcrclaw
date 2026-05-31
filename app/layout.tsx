import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GPCRclaw",
  description: "Campaign workbench for ECL2-focused GPCR nanobody design."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <nav style={{padding: '1rem', background: 'linear-gradient(90deg, #1e3a8a, #3b82f6)'}}>
          <a href="/" style={{marginRight: '1rem', color: '#fff', textDecoration: 'none', fontWeight: 'bold'}}>Home</a>
          <a href="/viewer" style={{color: '#fff', textDecoration: 'none', fontWeight: 'bold'}}>Viewer</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
