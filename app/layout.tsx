import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GPCRclaw",
  description: "Campaign workbench for ECL2-focused GPCR nanobody design."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
