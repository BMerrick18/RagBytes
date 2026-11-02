"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NAV_LINKS } from "@/lib/nav";
import { useEffect,useState } from "react";

export function SiteHeader() {
  const pathname = usePathname();
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const open = menuPath === pathname;

  function closeMenu() {
    setMenuPath(null);
  }

  function toggleMenu() {
    setMenuPath(open ? null : pathname);
  }

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuPath(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <>
        {open ? (
          <button
            type="button"
            aria-label="close menu"
            tabIndex={-1}
            className="fixed inset-0 z-10 md:hidden"
            onClick={closeMenu}
          />
    ) : null}
    <header className="sticky relative top-0 z-20 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur">

      {/* Mobile header */}
      <div className="grid h-[63px] grid-cols-[2.75rem_minmax(0,1fr)_2.75rem] items-center px-6 md:hidden">
        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={toggleMenu}
        >
          <svg viewBox="0 0 24 24" className={`h-5 w-5 transition-transform ${open ? "rotate-90" : ""}`} fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
           <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <Link href="/" className="flex min-h-11 items-center justify-self-center gap-2.5">
          <Logo className="h-8 w-8" />
          <span className="text-xl font-bold tracking-tight text-zinc-50">RagBytes</span>
        </Link>
        <div className="justify-self-end">
          <ThemeToggle />
        </div>
      </div>

      {open ? (
        <nav
          id="site-menu"
          aria-label="Main"
          className="absolute left-0 right-0 top-full border-b border-zinc-800 bg-zinc-950 px-6 py-2 md:hidden"
        >
          {NAV_LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={closeMenu}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 items-center rounded-md px-3 font-medium ${
                  active ? "bg-zinc-800 text-zinc-50" : "text-zinc-400"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      ) : null}

      {/* Desktop header */}
      <div className="hidden md:flex mx-auto w-full max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-6 py-3">
        <Link href="/" className="flex min-h-11 items-center gap-2.5 md:min-h-0">
          <Logo className="h-8 w-8" />
          <span className="text-xl font-bold tracking-tight text-zinc-50">RagBytes</span>
        </Link>
        <nav aria-label="Main" className="flex flex-wrap gap-1 text-sm">
          {NAV_LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`inline-flex min-h-11 items-center rounded-md px-3 py-1.5 font-medium transition-colors md:min-h-0 ${
                  active ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
    </>
  );
}
