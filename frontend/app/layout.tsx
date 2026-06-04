import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Domeggook → SmartStore 분석 MVP",
  description: "도매꾹 상품 HTML/URL을 분석해 스마트스토어 등록 초안을 미리 봅니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
