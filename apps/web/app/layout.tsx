import type { Metadata } from "next";
import { Inter, Inter_Tight } from "next/font/google";
import "./globals.css";
import "./evaluation.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body",
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "Settlewise — Finance Control",
  description: "Evidence-first Razorpay settlement reconciliation",
  applicationName: "Settlewise",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${interTight.variable}`}>{children}</body>
    </html>
  );
}
