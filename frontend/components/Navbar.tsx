"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

export default function Navbar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

  const navItems = [
    { name: "Dashboard", href: "/" },
    { name: "Documentation", href: "/review" },
    { name: "File Docs", href: "/file-docs" },
    { name: "Requirements", href: "/requirements" },
    { name: "Analytics", href: "/analytics" },
    { name: "Publish", href: "/publish" },
    { name: "Knowledge Base", href: "/knowledge-base" },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-border/40 bg-surface/95 backdrop-blur-md shadow-sm transition-all w-full">
      <div className="flex h-[88px] w-full items-center justify-between px-4 sm:px-10 lg:px-12">

        {/* Brand — Presidio style logo + wordmark with smooth motion hover */}
        <Link href="/" className="group flex items-center gap-3.5">
          <motion.div
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex h-11 w-11 flex-shrink-0 items-center justify-center"
          >
            <Image
              src="/logo.png?v=2"
              alt="DocuBear Logo"
              width={44}
              height={44}
              className="h-11 w-11 object-contain"
              priority
              unoptimized
            />
          </motion.div>
          <span className="text-xl font-bold tracking-tight text-text">
            Docu<span className="text-teal">Bear</span>
          </span>
        </Link>

        {/* Desktop Navigation with smooth sliding animated indicator */}
        <nav className="hidden md:flex items-center gap-2">
          {navItems.map((item) => {
            const isActive =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative px-4 py-2 text-[15px] font-medium transition-colors duration-200 ${
                  isActive ? "text-teal font-semibold" : "text-text/75 hover:text-text"
                }`}
              >
                <span>{item.name}</span>

                {/* Animated active underline indicator that glides smoothly across nav items */}
                {isActive && (
                  <motion.span
                    layoutId="navbar-active-indicator"
                    className="absolute bottom-0 left-3 right-3 h-[2.5px] rounded-full bg-teal"
                    transition={{
                      type: "spring",
                      stiffness: 400,
                      damping: 32,
                    }}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-3">
          {/* System status pill (hidden on small mobile) */}
          {/* <div className="hidden sm:flex items-center gap-2 rounded-full border border-text/30 px-4 py-2 text-xs sm:text-sm font-medium text-text/80 hover:border-text/60 transition-colors">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            Agent Active
          </div> */}

          {/* Primary CTA pill with motion scale */}
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Link
              href="/review"
              className="inline-flex items-center gap-2 rounded-full bg-text px-4 sm:px-6 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-xs transition-colors hover:bg-text/80"
            >
              Review Docs
            </Link>
          </motion.div>

          {/* Mobile Hamburger Toggle Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="flex md:hidden h-10 w-10 items-center justify-center rounded-full border border-border bg-canvas text-text hover:bg-surface transition-all"
            aria-label="Toggle mobile menu"
          >
            {mobileMenuOpen ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

      </div>

      {/* Mobile Slide-down Navigation Drawer */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="md:hidden overflow-hidden border-t border-border/40 bg-surface/98 backdrop-blur-lg px-6 py-4 shadow-lg"
          >
            <nav className="flex flex-col gap-2">
              {navItems.map((item) => {
                const isActive =
                  item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`flex items-center justify-between rounded-xl px-4 py-3 text-sm font-semibold transition-all ${
                      isActive
                        ? "bg-teal/10 text-teal border border-teal/20"
                        : "text-text hover:bg-canvas"
                    }`}
                  >
                    <span>{item.name}</span>
                    {isActive && (
                      <span className="h-2 w-2 rounded-full bg-teal" />
                    )}
                  </Link>
                );
              })}

              <div className="mt-2 pt-3 border-t border-border/60 flex items-center justify-between px-2 text-xs font-medium text-muted">
                <span className="flex items-center gap-2 text-emerald-700 font-bold">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  Agent System Active
                </span>
                <span>v1.0.0</span>
              </div>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
