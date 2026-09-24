"use client";

import { motion } from "framer-motion";
import { ReactNode } from "react";

interface AnimatedContainerProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  stagger?: number;
}

/**
  AnimatedContainer uses `whileInView` with `once: false` so elements
  smoothly stagger and slide up both on initial load AND when scrolling up/down.
*/
export function AnimatedContainer({
  children,
  className = "",
  delay = 0,
  stagger = 0.08,
}: AnimatedContainerProps) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: {
          transition: {
            staggerChildren: stagger,
            delayChildren: delay,
          },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

interface AnimatedItemProps {
  children: ReactNode;
  className?: string;
  y?: number;
  duration?: number;
}

export function AnimatedItem({
  children,
  className = "",
  y = 24,
  duration = 0.5,
}: AnimatedItemProps) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: y },
        show: {
          opacity: 1,
          y: 0,
          transition: {
            duration: duration,
            ease: [0.22, 1, 0.36, 1],
          },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

interface ScrollRevealProps {
  children: ReactNode;
  className?: string;
  y?: number;
  duration?: number;
  delay?: number;
}

/**
  ScrollReveal wraps standalone elements to animate them on scroll up & down.
*/
export function ScrollReveal({
  children,
  className = "",
  y = 28,
  duration = 0.55,
  delay = 0,
}: ScrollRevealProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: false, amount: 0.15 }}
      transition={{
        duration: duration,
        delay: delay,
        ease: [0.22, 1, 0.36, 1],
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
