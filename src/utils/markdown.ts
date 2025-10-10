// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Markdown rendering utilities
 */

import { marked } from 'marked';

// Configure marked for safe rendering
// Valid options: async, breaks, gfm, pedantic, renderer, silent, tokenizer, walkTokens
marked.setOptions({
  breaks: false, // Disable automatic line breaks to reduce blank lines
  gfm: true // GitHub Flavored Markdown
});

/**
 * Render markdown text to HTML
 * @param markdown - The markdown text to render
 * @returns HTML string
 */
export function renderMarkdown(markdown: string): string {
  if (!markdown) {
    return '';
  }

  try {
    // Use synchronous parse
    const result = marked(markdown);
    return typeof result === 'string' ? result : String(result);
  } catch (error) {
    console.error('Error rendering markdown:', error);
    return markdown; // Fallback to plain text
  }
}
