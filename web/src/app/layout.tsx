import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = "https://ragbytes.com";

const founder = {
  name: "Ben Merrick",
  url: "https://www.linkedin.com/in/ben-merrick-0835b4302/",
};

const previewImage = {
  url: "/og.png",
  width: 1200,
  height: 630,
  alt: "RagBytes",
  type: "image/png",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "RagBytes: embedding-ready document chunks",
    template: "%s · RagBytes",
  },
  description: "Upload documents and get clean chunks that are ready to embed.",
  authors: [founder],
  creator: founder.name,
  openGraph: {
    type: "website",
    siteName: "RagBytes",
    images: [previewImage],
  },
  twitter: {
    card: "summary_large_image",
    images: [previewImage],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <link rel="image_src" href={`${siteUrl}/og.png`} />
      </head>
      <body className="min-h-full flex flex-col">
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
