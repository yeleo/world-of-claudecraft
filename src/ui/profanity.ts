// Client-side cosmetic profanity masking for the chat log. The server ships the
// soft word list (in `hello` / `censor` frames) but never alters the text, so
// each client masks locally according to the player's "Filter Profanity"
// setting. This is display-only — slurs are blocked server-side and never get
// here, and a player who turns the filter off simply sees the raw text.
//
// The normalization MUST stay in lockstep with server/chat_filter.ts so the
// terms the server sends mask the same tokens the server intended. It's a tiny,
// stable function; the layering rules (ui/ can't import server/) make a small
// duplicate cleaner than a shared cross-boundary module.

const CONFUSABLE_CHARS: Record<string, string> = {
  '0': 'o',
  '1': 'i',
  '3': 'e',
  '4': 'a',
  '5': 's',
  '6': 'g',
  '7': 't',
  '8': 'b',
  '9': 'g',
  '!': 'i',
  '|': 'i',
  '@': 'a',
  $: 's',
  '+': 't',
  '©': 'c',
  '€': 'e',
  '£': 'l',
};

const CONFUSABLE_RE = /[0-9!|@$+©€£]/g;
const TOKEN_RE = /[\p{L}\p{M}\p{N}_@$!|+©€£]+/gu;
const HAS_CJK_RE = /[\u4e00-\u9fa5]/;

function foldConfusables(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(CONFUSABLE_RE, (ch) => CONFUSABLE_CHARS[ch] ?? ch);
}

function normalizeWord(term: string): string {
  return foldConfusables(term).replace(/[^a-z\u4e00-\u9fa5]/g, '');
}

/** Replace every token containing a soft term with asterisks of equal length. */
export function maskProfanity(text: string, terms: readonly string[]): string {
  if (terms.length === 0) return text;
  return text.replace(TOKEN_RE, (tok) => {
    const normalized = normalizeWord(tok);
    if (!normalized || !terms.some((term) => normalized.includes(term))) return tok;
    if (HAS_CJK_RE.test(tok)) {
      let masked = tok;
      for (const term of terms) {
        if (term && normalized.includes(term)) {
          masked = masked.split(term).join('*'.repeat(term.length));
        }
      }
      return masked;
    }
    return '*'.repeat(tok.length);
  });
}
