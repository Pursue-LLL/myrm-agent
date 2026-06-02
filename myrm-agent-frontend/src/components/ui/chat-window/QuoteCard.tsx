'use client';

import { X, Quote } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import useQuoteStore from '@/store/useQuoteStore';

const PREVIEW_MAX_LEN = 120;

export function QuoteCard() {
  const quote = useQuoteStore((s) => s.quote);
  const clearQuote = useQuoteStore((s) => s.clearQuote);

  return (
    <AnimatePresence>
      {quote && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className="overflow-hidden"
        >
          <div className="flex items-start gap-2 mb-2 px-1 py-2 rounded-full bg-primary/5 border border-primary/15">
            <Quote className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-primary/60" />
            <p className="text-xs text-muted-foreground leading-relaxed flex-1 line-clamp-3 break-all">
              {quote.quotedText.length > PREVIEW_MAX_LEN
                ? `${quote.quotedText.slice(0, PREVIEW_MAX_LEN)}…`
                : quote.quotedText}
            </p>
            <button
              type="button"
              onClick={clearQuote}
              className="flex-shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
            >
              <X className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
