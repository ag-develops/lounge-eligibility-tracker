import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Gatewise — Airport Lounge Eligibility",
  description: "Check airport lounge access, card spend conditions, and visit allowances before you travel.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
