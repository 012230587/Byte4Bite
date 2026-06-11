import type { Metadata } from "next";
import { Inter, Anton, Playfair_Display } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const inter = Inter({ subsets: ["latin"] });
const display = Anton({ subsets: ["latin"], weight: ["400"], variable: "--font-display" });
const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["700"],
  variable: "--font-brand",
});

export const metadata: Metadata = {
  title: "Byte4Bite | AI Recipe Generator",
  description: "Generate healthy recipes with AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${display.className} ${playfair.className} bg-slate-50 text-slate-900`}>
        <Navbar />
        <main>{children}</main>
      </body>
    </html>
  );
}